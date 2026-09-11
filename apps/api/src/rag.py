"""RAG fundamentado: somente evidências indexed e citações verificáveis.

O gerador desta fase é extrativo e determinístico. Não consulta conhecimento
externo nem transforma texto de documentos em instruções.
"""

# ruff: noqa: E501

from __future__ import annotations

import hashlib
import json
import re
import uuid
from typing import Annotated, Any

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import Field

from .academic import StrictModel, TokenDep, UserDep, _connect
from .config import Settings, get_settings
from .knowledge import _embed, _explicit_article_locator, rrf_merge

router = APIRouter(prefix="/api/v1/rag", tags=["grounded-rag"])


class RagRequest(StrictModel):
    query: str = Field(min_length=1, max_length=2000)
    subject_id: uuid.UUID | None = None
    source_id: uuid.UUID | None = None
    source_version_id: uuid.UUID | None = None
    limit: int = Field(default=5, ge=1, le=10)
    min_score: float = Field(default=0.0, ge=0.0, le=1.0)


def _injection(query: str) -> bool:
    return bool(re.search(r"ignore\s+(all|previous)\s+instructions|system\s+prompt|reveal\s+hidden", query, re.I))


def _tokens(value: str) -> set[str]:
    return {token for token in re.findall(r"[\wÀ-ÿ]+", value.casefold()) if len(token) >= 4}


_GENERIC_QUERY_TERMS = {
    "base", "diz", "sobre", "qual", "quais", "como", "pode", "podem",
    "falar", "explique", "mostra", "mostre", "informa", "informar",
}


def _supported_query(query: str, row: dict[str, Any], explicit: str | None) -> bool:
    terms = _tokens(query) - _GENERIC_QUERY_TERMS
    overlap = len(terms & _tokens(row["text"]))
    return bool(explicit and row["legal_locator"].rstrip(".") == explicit) or overlap >= 2


def _citation(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_name": row["source_title"],
        "locator": row["legal_locator"],
        "source_version_id": str(row["source_version_id"]),
        "chunk_id": str(row["id"]),
        "hash": row["content_sha256"],
        "official_url": row["canonical_url"],
        "lexical_rank": row.get("lexical_rank"),
        "vector_rank": row.get("vector_rank"),
        "rrf_score": row.get("rrf_score"),
    }


def verify_grounding(answer: dict[str, Any], evidence: list[dict[str, Any]]) -> dict[str, Any]:
    by_id = {str(row["id"]): row for row in evidence}
    citations = answer.get("citations", [])
    if answer.get("state") == "answered" and not citations:
        raise ValueError("answered_requires_citation")
    for citation in citations:
        row = by_id.get(str(citation.get("chunk_id")))
        if not row:
            raise ValueError("citation_not_in_evidence")
        if citation.get("locator") != row["legal_locator"] or citation.get("hash") != row["content_sha256"]:
            raise ValueError("citation_provenance_mismatch")
    return answer


def _retrieve(query: str, user_id: uuid.UUID, body: RagRequest, settings: Settings) -> tuple[list[dict[str, Any]], str, str]:
    vector, model_id, revision = _embed(query, settings)
    literal = "[" + ",".join(str(float(value)) for value in vector) + "]"
    filters = ["c.status='indexed'", "v.status='indexed'", "s.status='approved'", "s.owner_user_id=%s"]
    params: list[Any] = [user_id]
    if body.subject_id:
        filters.append("c.subject_id=%s")
        params.append(body.subject_id)
    if body.source_id:
        filters.append("s.id=%s")
        params.append(body.source_id)
    if body.source_version_id:
        filters.append("v.id=%s")
        params.append(body.source_version_id)
    where = " AND ".join(filters)
    common = """FROM mentor_concursos.knowledge_chunks c
        JOIN mentor_concursos.knowledge_source_versions v ON v.id=c.source_version_id
        JOIN mentor_concursos.knowledge_sources s ON s.id=v.source_id
        JOIN mentor_concursos.knowledge_embeddings e ON e.chunk_id=c.id"""
    explicit = _explicit_article_locator(query) or ""
    with _connect(settings) as connection:
        lexical = connection.execute(f"""SELECT c.id,c.text,c.normalized_text,c.legal_locator,c.content_sha256,
            s.id source_id,v.id source_version_id,s.title source_title,s.canonical_url,
            ts_rank_cd(c.search_vector, websearch_to_tsquery('portuguese', replace(%s,' ',' OR '))) lexical_score
            {common} WHERE {where} AND c.search_vector @@ websearch_to_tsquery('portuguese', replace(%s,' ',' OR '))
            ORDER BY CASE WHEN regexp_replace(c.legal_locator,'\\.$','')=%s THEN 0 ELSE 1 END,lexical_score DESC,c.id LIMIT %s""", [query, *params, query, explicit, body.limit * 4]).fetchall()
        vector_rows = connection.execute(f"""SELECT c.id,c.text,c.normalized_text,c.legal_locator,c.content_sha256,
            s.id source_id,v.id source_version_id,s.title source_title,s.canonical_url,
            1-(e.embedding <=> %s::vector) vector_score {common} WHERE {where}
            ORDER BY vector_score DESC,c.id LIMIT %s""", [literal, *params, body.limit * 4]).fetchall()
    merged = rrf_merge([dict(row) for row in lexical], [dict(row) for row in vector_rows], body.limit, k=20, lexical_weight=1.0)
    return [row for row in merged if max(float(row.get("lexical_score") or 0), float(row.get("vector_score") or 0)) >= body.min_score], model_id, revision


@router.post("/answer")
def answer(request: Request, body: RagRequest, user: UserDep, _: TokenDep, settings: Annotated[Settings, Depends(get_settings)]) -> dict[str, Any]:
    if _injection(body.query):
        return {"state": "insufficient_evidence", "answer": "A pergunta não contém uma solicitação acadêmica fundamentável nas fontes indexadas.", "citations": [], "request_id": request.state.request_id}
    try:
        evidence, model_id, revision = _retrieve(body.query, user.id, body, settings)
    except (HTTPException, OSError, KeyError, ValueError, psycopg.Error):
        return {
            "state": "retrieval_failed",
            "answer": "Não foi possível recuperar evidências com segurança.",
            "citations": [],
            "request_id": request.state.request_id,
        }
    lexical_evidence = [row for row in evidence if row.get("lexical_rank") is not None]
    explicit = _explicit_article_locator(body.query)
    supported = any(
        row.get("lexical_score", 0) >= 0.1
        and _supported_query(body.query, row, explicit)
        for row in lexical_evidence
    )
    citations = [_citation(row) for row in evidence[: min(3, len(evidence))]] if supported else []
    if not supported:
        result = {"state": "insufficient_evidence", "answer": "As fontes indexadas não oferecem evidência suficiente para responder com segurança.", "citations": [], "model_id": model_id, "model_revision": revision, "request_id": request.state.request_id}
    else:
        snippets = [row["text"][:700] for row in evidence[: min(3, len(evidence))]]
        result = {"state": "answered", "answer": "Resposta fundamentada exclusivamente nos trechos recuperados:\n\n" + "\n\n".join(snippets), "citations": citations, "model_id": model_id, "model_revision": revision, "request_id": request.state.request_id}
    try:
        verify_grounding(result, evidence)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail="Falha de verificação de fundamentação") from exc
    with _connect(settings) as connection, connection.transaction():
        connection.execute("INSERT INTO mentor_concursos.retrieval_audit(user_id,query_hash,filters,returned_chunk_ids,scores,model_id,model_revision,request_id) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)", (user.id, hashlib.sha256(body.query.strip().lower().encode()).hexdigest(), json.dumps({"rag": True, "source_id": str(body.source_id) if body.source_id else None}), [row["id"] for row in evidence], json.dumps([_citation(row) for row in evidence]), model_id, revision, request.state.request_id))
    return result
