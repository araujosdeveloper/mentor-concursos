"""Executor controlado do pipeline; sem execução automática em produção."""

# ruff: noqa: E501

from __future__ import annotations

import json
import logging
import os
import time
import urllib.request
import uuid
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

from .knowledge import chunk_text, normalize_text

LOGGER = logging.getLogger(__name__)
DOCUMENT_ROOT = Path(os.getenv("DOCUMENT_ROOT", "/var/lib/mentor-concursos/documents"))


def connect() -> psycopg.Connection:
    return psycopg.connect(
        host=os.environ["DATABASE_HOST"],
        port=int(os.getenv("DATABASE_PORT", "5432")),
        dbname=os.environ["DATABASE_NAME"],
        user=os.environ["DATABASE_USER"],
        password=os.environ["DATABASE_PASSWORD"],
        row_factory=dict_row,
    )


def claim_job(
    worker_id: str, supported_source_types: tuple[str, ...], lease_seconds: int = 300
) -> dict[str, object] | None:
    """Adquire apenas jobs suportados; leases expirados podem ser retomados."""
    if not supported_source_types:
        return None
    with connect() as connection, connection.transaction():
        row = connection.execute(
            """SELECT j.*,s.source_type FROM mentor_concursos.ingestion_jobs j
               JOIN mentor_concursos.knowledge_source_versions v ON v.id=j.source_version_id
               JOIN mentor_concursos.knowledge_sources s ON s.id=v.source_id
               WHERE s.source_type = ANY(%s)
               AND (j.status='queued' OR (j.status NOT IN ('completed','failed','cancelled')
               AND j.lease_expires_at < CURRENT_TIMESTAMP))
               AND j.attempts < 5
               AND (j.next_attempt_at IS NULL OR j.next_attempt_at <= CURRENT_TIMESTAMP)
               ORDER BY j.created_at,j.id FOR UPDATE OF j SKIP LOCKED LIMIT 1""",
            (list(supported_source_types),),
        ).fetchone()
        if not row:
            return None
        claimed = connection.execute(
            """UPDATE mentor_concursos.ingestion_jobs
               SET status='validating',stage='validating',attempts=attempts+1,
                   lease_owner=%s,lease_expires_at=CURRENT_TIMESTAMP + (%s || ' seconds')::interval
               WHERE id=%s RETURNING *""",
            (worker_id, lease_seconds, row["id"]),
        ).fetchone()
        connection.execute("INSERT INTO mentor_concursos.ingestion_events(job_id,stage,result) VALUES (%s,'validating','started')", (row["id"],))
        return claimed


def embed_batch(texts: list[str], endpoint: str = "http://mentor-concursos-embeddings:8090") -> dict[str, object]:
    payload = urllib.request.Request(
        f"{endpoint.rstrip('/')}/embed",
        data=(('{"texts":' + json.dumps(texts) + ',"prefix":"passage:"}').encode()),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(payload, timeout=10) as response:
        return json.loads(response.read(2 * 1024 * 1024))


def process_fixture_text(job_id: uuid.UUID, text: str, worker_id: str = "fixture-worker") -> int:
    """Processa texto sintético em transação; não lê arquivos reais por padrão."""
    started = time.monotonic()
    normalized = normalize_text(text)
    chunks = chunk_text(normalized)
    if not chunks:
        raise ValueError("empty_extraction")
    with connect() as connection, connection.transaction():
        job = connection.execute("SELECT * FROM mentor_concursos.ingestion_jobs WHERE id=%s FOR UPDATE", (job_id,)).fetchone()
        if not job or job["lease_owner"] not in (None, worker_id):
            raise ValueError("job_not_owned")
        connection.execute("UPDATE mentor_concursos.ingestion_jobs SET status='chunking',stage='chunking',lease_owner=%s WHERE id=%s", (worker_id, job_id))
        for chunk in chunks:
            connection.execute(
                """INSERT INTO mentor_concursos.knowledge_chunks
                   (source_version_id,ordinal,text,normalized_text,content_sha256,character_count,token_count,metadata)
                   SELECT source_version_id,%s,%s,%s,%s,%s,%s,%s FROM mentor_concursos.ingestion_jobs WHERE id=%s
                   ON CONFLICT (source_version_id,ordinal) DO NOTHING""",
                (chunk["ordinal"], chunk["text"], chunk["normalized_text"], chunk["content_sha256"], chunk["character_count"], chunk["token_count"], json.dumps({"prompt_injection_suspected": chunk["prompt_injection_suspected"], "algorithm": chunk["algorithm"]}), job_id),
            )
        connection.execute("UPDATE mentor_concursos.ingestion_jobs SET status='pending_review',stage='reviewing',lease_owner=NULL,lease_expires_at=NULL WHERE id=%s", (job_id,))
        connection.execute("UPDATE mentor_concursos.knowledge_source_versions SET status='pending_review' WHERE id=%s", (job["source_version_id"],))
        connection.execute("INSERT INTO mentor_concursos.ingestion_events(job_id,stage,result,duration_ms) VALUES (%s,'chunking','succeeded',%s)", (job_id, int((time.monotonic() - started) * 1000)))
    return len(chunks)
