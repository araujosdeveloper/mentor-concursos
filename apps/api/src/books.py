"""Ingestão de livros do usuário para estudo pessoal (RAG).

O livro é material próprio do usuário: entra como fonte aprovada/indexada
(sem revisão humana), separado das fontes externas.
"""

# ruff: noqa: E501

from __future__ import annotations

import json
import urllib.request
from typing import Annotated, Any

import psycopg
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse

from apps.worker.src.knowledge import (
    MODEL_ID,
    MODEL_REVISION,
    DocumentRejected,
    chunk_text,
    normalize_text,
    validate_document,
)

from .academic import TokenDep, UserDep, _audit, _mutate, _row_response
from .config import Settings, get_settings

router = APIRouter(prefix="/api/v1/books", tags=["books"])

_EMBED_BATCH = 8


def _tika_extract(data: bytes, tika_url: str) -> str:
    request = urllib.request.Request(
        f"{tika_url.rstrip('/')}/tika",
        data=data,
        headers={"Accept": "text/plain", "Content-Type": "application/pdf"},
        method="PUT",
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        text = response.read(50 * 1024 * 1024).decode("utf-8", "replace")
    if not text.strip():
        raise ValueError("empty_extraction")
    return text


def _embed_passages(texts: list[str], embeddings_url: str) -> list[list[float]]:
    vectors: list[list[float]] = []
    for offset in range(0, len(texts), _EMBED_BATCH):
        batch = texts[offset : offset + _EMBED_BATCH]
        request = urllib.request.Request(
            f"{embeddings_url.rstrip('/')}/embed",
            data=json.dumps({"texts": batch, "prefix": "passage:"}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            body = json.loads(response.read(16 * 1024 * 1024))
        batch_vectors = body.get("vectors")
        if not isinstance(batch_vectors, list) or len(batch_vectors) != len(batch):
            raise ValueError("embedding_contract_invalid")
        vectors.extend(batch_vectors)
    if any(len(vector) != 384 for vector in vectors):
        raise ValueError("embedding_dimension_invalid")
    return vectors


@router.post("", status_code=201)
def upload_book(
    request: Request,
    file: Annotated[UploadFile, File(...)],
    title: Annotated[str, Form(min_length=1, max_length=500)],
    user: UserDep,
    _: TokenDep,
    settings: Annotated[Settings, Depends(get_settings)],
) -> JSONResponse:
    data = file.file.read()
    try:
        doc = validate_document(data, file.content_type, file.filename or "livro.pdf")
    except DocumentRejected as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    try:
        extracted = _tika_extract(doc.data, settings.tika_url)
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=502, detail="Falha ao extrair o texto do PDF") from exc
    chunks = chunk_text(normalize_text(extracted.replace("\f", "\n")))
    if not chunks:
        raise HTTPException(status_code=422, detail="Nenhum texto extraído do documento")
    vectors = _embed_passages([str(item["text"]) for item in chunks], settings.embeddings_url)

    def operation(connection: psycopg.Connection) -> tuple[int, dict[str, Any]]:
        source = connection.execute(
            "INSERT INTO mentor_concursos.knowledge_sources(owner_user_id,source_type,title,license_status,trust_level,status) "
            "VALUES (%s,'manual',%s,'allowed','trusted','approved') RETURNING *",
            (user.id, title),
        ).fetchone()
        version = connection.execute(
            "INSERT INTO mentor_concursos.knowledge_source_versions(source_id,version_label,sha256,mime_type,byte_size,storage_key,status) "
            "VALUES (%s,'v1',%s,%s,%s,%s,'indexed') RETURNING *",
            (source["id"], doc.sha256, doc.mime_type, doc.byte_size, f"user-books/{doc.sha256}"),
        ).fetchone()
        for ordinal, (chunk, vector) in enumerate(zip(chunks, vectors, strict=True)):
            row = connection.execute(
                "INSERT INTO mentor_concursos.knowledge_chunks(source_version_id,ordinal,text,normalized_text,content_sha256,character_count,token_count,status,metadata) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,'indexed',%s) RETURNING id",
                (version["id"], ordinal, chunk["text"], chunk["normalized_text"], chunk["content_sha256"], chunk["character_count"], chunk["token_count"], json.dumps({"prompt_injection_suspected": chunk["prompt_injection_suspected"], "algorithm": chunk["algorithm"]})),
            ).fetchone()
            literal = "[" + ",".join(str(float(value)) for value in vector) + "]"
            connection.execute(
                "INSERT INTO mentor_concursos.knowledge_embeddings(chunk_id,model_id,model_revision,dimensions,embedding,normalized,content_sha256) "
                "VALUES (%s,%s,%s,384,%s::vector,true,%s)",
                (row["id"], MODEL_ID, MODEL_REVISION, literal, chunk["content_sha256"]),
            )
        _audit(connection, "user", "book_ingested", "knowledge_sources", source["id"], request.state.request_id, {"chunks": len(chunks), "title": title})
        return 201, {"source": _row_response(source), "version": _row_response(version), "chunks": len(chunks)}

    return _mutate(request, user, settings, {"title": title, "sha256": doc.sha256}, operation)
