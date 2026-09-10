"""Processa uma fonte oficial já colocada em quarentena.

Este comando é deliberadamente explícito: recebe apenas uma versão/job já
registrados, usa Tika e o serviço de embeddings internos, e deixa chunks e
versão em pending_review. Nunca promove conteúdo a indexed.
"""

# ruff: noqa: E501

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
import urllib.request
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

from apps.worker.src.knowledge import MODEL_ID, MODEL_REVISION, normalize_text

ARTICLE_RE = re.compile(r"(?m)^(Art\.\s+\d+[ºo]?\.?)(.*?)(?=^Art\.\s+\d+[ºo]?\.?|\Z)", re.S)
MAX_CHARS = 1400


def db() -> psycopg.Connection:
    return psycopg.connect(
        host=os.environ["DATABASE_HOST"],
        port=int(os.getenv("DATABASE_PORT", "5432")),
        dbname=os.environ["DATABASE_NAME"],
        user=os.environ["DATABASE_USER"],
        password=os.environ["DATABASE_PASSWORD"],
        row_factory=dict_row,
    )


def tika_extract(data: bytes) -> str:
    req = urllib.request.Request(
        "http://mentor-concursos-tika:9998/tika",
        data=data,
        headers={"Accept": "text/plain", "Content-Type": "application/pdf"},
        method="PUT",
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        text = response.read(2 * 1024 * 1024).decode("utf-8")
    if not text.strip():
        raise RuntimeError("empty_extraction")
    return text


def normative_chunks(text: str) -> list[dict[str, object]]:
    normalized = normalize_text(text.replace("\f", "\n"))
    if not normalized:
        raise RuntimeError("empty_normalized_text")
    matches = list(ARTICLE_RE.finditer(normalized))
    if not matches:
        raise RuntimeError("articles_not_detected")
    preamble = normalized[: matches[0].start()].strip()
    blocks = ([preamble] if preamble else []) + [match.group(0).strip() for match in matches]
    result: list[dict[str, object]] = []
    for block in blocks:
        locator_match = re.match(r"(Art\.\s+\d+[ºo]?\.?)", block)
        locator = locator_match.group(1) if locator_match else "title-and-preamble"
        if len(block) <= MAX_CHARS:
            pieces = [block]
        else:
            lines = [line.strip() for line in block.splitlines() if line.strip()]
            pieces: list[str] = []
            current = ""
            for line in lines:
                candidate = f"{current}\n{line}".strip() if current else line
                if current and len(candidate) > MAX_CHARS:
                    pieces.append(current)
                    current = f"{locator}\n{line}"
                else:
                    current = candidate
            if current:
                pieces.append(current)
        for piece in pieces:
            value = normalize_text(piece)
            result.append({
                "text": value,
                "normalized_text": value,
                "locator": locator,
                "section_path": [locator],
                "content_sha256": hashlib.sha256(value.encode()).hexdigest(),
                "character_count": len(value),
                "token_count": max(1, len(value.split())),
                "prompt_injection_suspected": bool(re.search(r"ignore\s+(all|previous)\s+instructions|system\s+prompt|execute\s+this\s+command", value, re.I)),
            })
    if not result or any(not item["text"] for item in result):
        raise RuntimeError("invalid_chunks")
    return result


def embed(texts: list[str]) -> dict[str, object]:
    req = urllib.request.Request(
        "http://mentor-concursos-embeddings:8090/embed",
        data=json.dumps({"texts": texts, "prefix": "passage:"}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        body = json.loads(response.read(2 * 1024 * 1024))
    vectors = body.get("vectors")
    if not isinstance(vectors, list) or len(vectors) != len(texts) or any(len(vector) != 384 for vector in vectors):
        raise RuntimeError("embedding_contract_invalid")
    return body


def main() -> None:
    if len(sys.argv) != 4:
        raise SystemExit("usage: process-pilot-source.py STORAGE_PATH VERSION_ID JOB_ID")
    storage_path, version_id, job_id = sys.argv[1:]
    root = Path(os.getenv("DOCUMENT_ROOT", "/var/lib/mentor-concursos/documents"))
    source_file = root / storage_path
    data = source_file.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    started = time.monotonic()
    extracted = tika_extract(data)
    normalized = normalize_text(extracted.replace("\f", "\n"))
    chunks = normative_chunks(normalized)
    extracted_path = root / "extracted" / f"{digest}.txt"
    extracted_path.parent.mkdir(parents=True, exist_ok=True)
    extracted_path.write_text(normalized, encoding="utf-8")
    extracted_path.chmod(0o600)
    vectors: list[list[float]] = []
    # Lotes pequenos mantêm a margem de memória do runtime ONNX aprovado.
    for offset in range(0, len(chunks), 2):
        vectors.extend(embed([str(item["text"]) for item in chunks[offset : offset + 2]])["vectors"])
    with db() as connection, connection.transaction():
        version = connection.execute("SELECT * FROM mentor_concursos.knowledge_source_versions WHERE id=%s FOR UPDATE", (version_id,)).fetchone()
        if not version or version["sha256"] != digest or version["status"] not in {"quarantined", "validated", "extracted", "normalized", "chunked", "embedded"}:
            raise RuntimeError("version_quarantine_or_hash_mismatch")
        subject = connection.execute("SELECT id FROM mentor_concursos.subjects WHERE name='Direito Administrativo'").fetchone()
        if not subject:
            raise RuntimeError("subject_not_found")
        connection.execute("UPDATE mentor_concursos.knowledge_source_versions SET status='validated', extraction_metadata=extraction_metadata || %s::jsonb WHERE id=%s", (json.dumps({"extracted_sha256": hashlib.sha256(normalized.encode()).hexdigest(), "extracted_characters": len(normalized), "tika_version": "3.2.2", "article_count": len(re.findall(r"(?m)^Art\.", normalized)), "extracted_storage_key": f"extracted/{digest}.txt"}), version_id))
        for ordinal, (chunk, vector) in enumerate(zip(chunks, vectors, strict=True)):
            row = connection.execute("INSERT INTO mentor_concursos.knowledge_chunks(source_version_id,subject_id,ordinal,text,normalized_text,content_sha256,section_path,legal_locator,character_count,token_count,status,metadata) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'pending_review',%s) ON CONFLICT (source_version_id,ordinal) DO UPDATE SET text=EXCLUDED.text RETURNING id", (version_id, subject["id"], ordinal, chunk["text"], chunk["normalized_text"], chunk["content_sha256"], chunk["section_path"], chunk["locator"], chunk["character_count"], chunk["token_count"], json.dumps({"prompt_injection_suspected": chunk["prompt_injection_suspected"], "algorithm": "normative-article-v1"}))).fetchone()
            literal = "[" + ",".join(str(float(value)) for value in vector) + "]"
            connection.execute("INSERT INTO mentor_concursos.knowledge_embeddings(chunk_id,model_id,model_revision,dimensions,embedding,normalized,content_sha256) VALUES (%s,%s,%s,384,%s::vector,true,%s) ON CONFLICT (chunk_id,model_id,model_revision) DO NOTHING", (row["id"], MODEL_ID, MODEL_REVISION, literal, chunk["content_sha256"]))
        connection.execute("UPDATE mentor_concursos.knowledge_source_versions SET status='pending_review' WHERE id=%s", (version_id,))
        connection.execute("UPDATE mentor_concursos.knowledge_sources SET status='pending_review' WHERE id=(SELECT source_id FROM mentor_concursos.knowledge_source_versions WHERE id=%s)", (version_id,))
        connection.execute("UPDATE mentor_concursos.ingestion_jobs SET status='completed',stage='reviewing',lease_owner=NULL,lease_expires_at=NULL,updated_at=CURRENT_TIMESTAMP WHERE id=%s", (job_id,))
        connection.execute("INSERT INTO mentor_concursos.ingestion_events(job_id,stage,result,duration_ms,metadata) VALUES (%s,'reviewing','succeeded',%s,%s)", (job_id, int((time.monotonic() - started) * 1000), json.dumps({"chunks": len(chunks), "embeddings": len(vectors), "extracted_sha256": hashlib.sha256(normalized.encode()).hexdigest()})))
    print(json.dumps({"chunks": len(chunks), "embeddings": len(vectors), "extracted_sha256": hashlib.sha256(normalized.encode()).hexdigest(), "status": "pending_review"}))


if __name__ == "__main__":
    main()
