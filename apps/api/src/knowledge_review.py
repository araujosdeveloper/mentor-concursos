"""Revisão transacional e idempotente de versões de conhecimento."""

from __future__ import annotations

import json
import uuid
from typing import Any

from fastapi import HTTPException

from .academic import _audit

APPROVED_MODEL_ID = "intfloat/multilingual-e5-small"
APPROVED_MODEL_REVISION = "fd1525a9fd15316a2d503bf26ab031a61d056e98"
APPROVED_DIMENSIONS = 384
REVIEWER_ROLES = {"source_reviewer", "admin"}


def _existing_review(
    connection: Any,
    version_id: uuid.UUID,
    decision: str,
    version_status: str,
    source_status: str,
) -> dict[str, Any] | None:
    reviews = connection.execute(
        """SELECT * FROM mentor_concursos.source_reviews
           WHERE source_version_id=%s ORDER BY created_at,id FOR UPDATE""",
        (version_id,),
    ).fetchall()
    if not reviews:
        return None
    expected_status = "indexed" if decision == "approved" else "rejected"
    decisions = {row["decision"] for row in reviews}
    chunk_states = connection.execute(
        """SELECT status FROM mentor_concursos.knowledge_chunks
           WHERE source_version_id=%s ORDER BY id FOR UPDATE""",
        (version_id,),
    ).fetchall()
    source_consistent = decision != "approved" or source_status == "approved"
    chunks_consistent = bool(chunk_states) and all(
        chunk["status"] == expected_status for chunk in chunk_states
    )
    if (
        decisions == {decision}
        and len(reviews) == 1
        and version_status == expected_status
        and source_consistent
        and chunks_consistent
    ):
        return reviews[0]
    raise HTTPException(status_code=409, detail="Decisão de revisão conflitante")


def review_knowledge_version(
    connection: Any,
    *,
    version_id: uuid.UUID,
    reviewer_id: uuid.UUID,
    decision: str,
    reason: str,
    request_id: str,
) -> dict[str, Any]:
    """Executa dentro da transação aberta pelo chamador; qualquer erro reverte tudo."""
    row = connection.execute(
        """SELECT v.*,s.status AS source_status,s.owner_user_id,u.role
           FROM mentor_concursos.knowledge_source_versions v
           JOIN mentor_concursos.knowledge_sources s ON s.id=v.source_id
           JOIN mentor_concursos.users u ON u.id=%s
           WHERE v.id=%s FOR UPDATE OF s,v""",
        (reviewer_id, version_id),
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Versão não encontrada")
    if row["role"] not in REVIEWER_ROLES:
        raise HTTPException(status_code=403, detail="Permissão insuficiente")
    if row["role"] == "source_reviewer" and row["owner_user_id"] != reviewer_id:
        raise HTTPException(status_code=404, detail="Versão não encontrada")

    replay = _existing_review(connection, version_id, decision, row["status"], row["source_status"])
    if replay is not None:
        return replay
    if row["status"] in {"rejected", "superseded", "indexed"}:
        raise HTTPException(status_code=409, detail="Versão não está pendente")
    if row["status"] != "pending_review":
        raise HTTPException(status_code=409, detail="Versão não está pendente")

    source_id = row["source_id"]
    chunks = connection.execute(
        """SELECT c.id,c.status,c.metadata,
                  EXISTS (
                    SELECT 1 FROM mentor_concursos.knowledge_embeddings e
                    WHERE e.chunk_id=c.id AND e.dimensions=%s
                      AND e.model_id=%s AND e.model_revision=%s
                  ) AS approved_embedding
           FROM mentor_concursos.knowledge_chunks c
           WHERE c.source_version_id=%s ORDER BY c.id FOR UPDATE OF c""",
        (APPROVED_DIMENSIONS, APPROVED_MODEL_ID, APPROVED_MODEL_REVISION, version_id),
    ).fetchall()

    previous = connection.execute(
        """SELECT id FROM mentor_concursos.knowledge_source_versions
           WHERE source_id=%s AND id<>%s AND status='indexed'
           ORDER BY created_at DESC,id FOR UPDATE""",
        (source_id, version_id),
    ).fetchall()

    if decision == "approved":
        if not chunks:
            raise HTTPException(status_code=409, detail="Versão sem chunks")
        if any(chunk["status"] != "pending_review" for chunk in chunks):
            raise HTTPException(status_code=409, detail="Chunks não estão integralmente pendentes")
        if any(not chunk["approved_embedding"] for chunk in chunks):
            raise HTTPException(
                status_code=409, detail="Embedding aprovado ausente ou incompatível"
            )
        if any(
            bool((chunk["metadata"] or {}).get("prompt_injection_suspected")) for chunk in chunks
        ):
            raise HTTPException(status_code=409, detail="Chunk suspeito requer quarentena")

    review = connection.execute(
        """INSERT INTO mentor_concursos.source_reviews
           (source_id,source_version_id,reviewer,decision,reason)
           VALUES (%s,%s,%s,%s,%s) RETURNING *""",
        (source_id, version_id, reviewer_id, decision, reason),
    ).fetchone()

    if decision == "approved":
        connection.execute(
            """UPDATE mentor_concursos.knowledge_chunks SET status='indexed'
               WHERE source_version_id=%s AND status='pending_review'""",
            (version_id,),
        )
        connection.execute(
            "UPDATE mentor_concursos.knowledge_source_versions SET status='indexed' WHERE id=%s",
            (version_id,),
        )
        connection.execute(
            "UPDATE mentor_concursos.knowledge_sources SET status='approved' WHERE id=%s",
            (source_id,),
        )
        for old in previous:
            connection.execute(
                """UPDATE mentor_concursos.knowledge_chunks SET status='rejected'
                   WHERE source_version_id=%s""",
                (old["id"],),
            )
            connection.execute(
                """UPDATE mentor_concursos.knowledge_source_versions
                   SET status='superseded' WHERE id=%s""",
                (old["id"],),
            )
        event_stage = "approved"
    else:
        connection.execute(
            """UPDATE mentor_concursos.knowledge_chunks SET status='rejected'
               WHERE source_version_id=%s AND status='pending_review'""",
            (version_id,),
        )
        connection.execute(
            "UPDATE mentor_concursos.knowledge_source_versions SET status='rejected' WHERE id=%s",
            (version_id,),
        )
        if not previous:
            connection.execute(
                "UPDATE mentor_concursos.knowledge_sources SET status='rejected' WHERE id=%s",
                (source_id,),
            )
        event_stage = "rejected"

    metadata = {"decision": decision, "reviewer_id": str(reviewer_id)}
    _audit(
        connection,
        "user",
        "knowledge_version_reviewed",
        "knowledge_source_versions",
        version_id,
        request_id,
        metadata,
    )
    connection.execute(
        """INSERT INTO mentor_concursos.ingestion_events(job_id,stage,result,metadata)
           SELECT id,%s,'succeeded',%s FROM mentor_concursos.ingestion_jobs
           WHERE source_version_id=%s ORDER BY created_at DESC,id LIMIT 1""",
        (event_stage, json.dumps({"request_id": request_id, **metadata}), version_id),
    )
    return review
