"""Promove exclusivamente a fonte piloto após conferência humana explícita."""

# ruff: noqa: E501

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

SOURCE_ID = "b4956e62-aee5-4f25-ba0b-50048a7ede60"
VERSION_ID = "1eccd249-b219-4d96-8e36-5dba1535159e"
PDF_SHA256 = "d698c78220576ffa3981b89e001a28f25114f4a9e05fb241e04dcdaadfcd1b65"
TEXT_SHA256 = "c2cf5b1aef775d066539efb59711a8d97625109deaf7c1aaa0defb22a54c8e8f"
MODEL_ID = "intfloat/multilingual-e5-small"
MODEL_REVISION = "fd1525a9fd15316a2d503bf26ab031a61d056e98"
DOCUMENT_ROOT = Path(os.getenv("DOCUMENT_ROOT", "/var/lib/mentor-concursos/documents"))
PDF = DOCUMENT_ROOT / "quarantine" / "045f3eca46914e2fa4377aa71f463691" / f"{PDF_SHA256}.pdf"
TEXT = DOCUMENT_ROOT / "extracted" / f"{PDF_SHA256}.txt"
REQUEST_ID = "human-approval-20260910"
COMMIT = "264ec35e93acea77f7ccd74a2133c5c77caf28"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    if sha256(PDF) != PDF_SHA256 or sha256(TEXT) != TEXT_SHA256:
        raise SystemExit("hash_mismatch_before_promotion")
    connection = psycopg.connect(
        host=os.environ["DATABASE_HOST"], port=int(os.getenv("DATABASE_PORT", "5432")),
        dbname=os.environ["DATABASE_NAME"], user=os.environ["DATABASE_USER"],
        password=os.environ["DATABASE_PASSWORD"], row_factory=dict_row,
    )
    with connection, connection.transaction():
        version = connection.execute("""
            SELECT v.*, s.status AS source_status FROM mentor_concursos.knowledge_source_versions v
            JOIN mentor_concursos.knowledge_sources s ON s.id=v.source_id
            WHERE v.id=%s AND s.id=%s FOR UPDATE
        """, (VERSION_ID, SOURCE_ID)).fetchone()
        if not version:
            raise SystemExit("pilot_ids_not_found")
        approved_review = connection.execute("SELECT 1 FROM mentor_concursos.source_reviews WHERE source_version_id=%s AND decision='approved'", (VERSION_ID,)).fetchone()
        if version["status"] == "indexed" and approved_review:
            print(json.dumps({"status": "already-approved", "version_id": VERSION_ID}))
            return
        if version["status"] != "pending_review" or version["source_status"] != "pending_review":
            raise SystemExit("invalid_pending_review_state")
        if version["sha256"] != PDF_SHA256 or version["extraction_metadata"].get("extracted_sha256") != TEXT_SHA256:
            raise SystemExit("database_hash_mismatch")
        chunks = connection.execute("SELECT id FROM mentor_concursos.knowledge_chunks WHERE source_version_id=%s AND status='pending_review' AND metadata->>'algorithm'='normative-article-v2' ORDER BY ordinal", (VERSION_ID,)).fetchall()
        total_chunks = connection.execute("SELECT count(*) AS n FROM mentor_concursos.knowledge_chunks WHERE source_version_id=%s", (VERSION_ID,)).fetchone()["n"]
        embedded = connection.execute("""
            SELECT count(*) AS n FROM mentor_concursos.knowledge_embeddings e
            JOIN mentor_concursos.knowledge_chunks c ON c.id=e.chunk_id
            WHERE c.source_version_id=%s AND e.model_id=%s AND e.model_revision=%s AND e.dimensions=384
        """, (VERSION_ID, MODEL_ID, MODEL_REVISION)).fetchone()["n"]
        if total_chunks != 84 or len(chunks) != 84 or embedded != 84:
            raise SystemExit("pilot_count_or_embedding_mismatch")
        reviewer = connection.execute("SELECT id FROM mentor_concursos.users WHERE name='Roberto Araujo'").fetchall()
        if len(reviewer) != 1:
            raise SystemExit("reviewer_not_unambiguous")
        reviewer_id = reviewer[0]["id"]
        connection.execute("""
            INSERT INTO mentor_concursos.source_reviews(source_id,source_version_id,reviewer,decision,reason)
            VALUES (%s,%s,%s,'approved',%s)
        """, (SOURCE_ID, VERSION_ID, reviewer_id, "Fonte oficial conferida para indexação piloto controlada."))
        connection.execute("UPDATE mentor_concursos.knowledge_chunks SET status='indexed' WHERE source_version_id=%s AND status='pending_review'", (VERSION_ID,))
        connection.execute("UPDATE mentor_concursos.knowledge_source_versions SET status='indexed' WHERE id=%s", (VERSION_ID,))
        connection.execute("UPDATE mentor_concursos.knowledge_sources SET status='approved' WHERE id=%s", (SOURCE_ID,))
        metadata = {"decision": "approved", "reviewer": "Roberto Araujo", "policy_version": "human-review-v1", "pdf_sha256": PDF_SHA256, "text_sha256": TEXT_SHA256, "model_id": MODEL_ID, "model_revision": MODEL_REVISION, "dimensions": 384, "application_commit": COMMIT}
        connection.execute("INSERT INTO mentor_concursos.audit_events(actor,action,entity,entity_id,request_id,metadata) VALUES ('human:Roberto Araujo','knowledge_source_approved','knowledge_source_versions',%s,%s,%s)", (VERSION_ID, REQUEST_ID, json.dumps(metadata)))
        job = connection.execute("SELECT id FROM mentor_concursos.ingestion_jobs WHERE source_version_id=%s ORDER BY created_at DESC LIMIT 1", (VERSION_ID,)).fetchone()
        if job:
            connection.execute("INSERT INTO mentor_concursos.ingestion_events(job_id,stage,result,metadata) VALUES (%s,'approved','succeeded',%s)", (job["id"], json.dumps({"chunks": 84, "embeddings": 84, "reviewer": "human", "request_id": REQUEST_ID})))
        print(json.dumps({"status": "indexed", "source_id": SOURCE_ID, "version_id": VERSION_ID, "chunks": 84, "embeddings": 84}))


if __name__ == "__main__":
    main()
