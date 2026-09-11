"""API interna para proveniência, ingestão e recuperação sem geração de texto."""

# ruff: noqa: E501

from __future__ import annotations

import hashlib
import json
import re
import urllib.request
import uuid
from typing import Annotated, Any

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import Field

from .academic import StrictModel, TokenDep, UserDep, _audit, _connect, _mutate, _row_response
from .config import Settings, get_settings

router = APIRouter(prefix="/api/v1/knowledge", tags=["knowledge"])


class SourceCreate(StrictModel):
    source_type: str = Field(pattern=r"^(law|notice|manual|exam|synthetic)$")
    title: str = Field(min_length=1, max_length=500)
    issuer: str | None = Field(default=None, max_length=300)
    authority: str | None = Field(default=None, max_length=300)
    canonical_url: str | None = Field(default=None, pattern=r"^https?://")
    license_status: str = Field(pattern=r"^(unknown|allowed|restricted|denied)$")
    trust_level: str = Field(default="untrusted", pattern=r"^(untrusted|review|trusted)$")
    subject_id: uuid.UUID | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class VersionCreate(StrictModel):
    version_label: str = Field(min_length=1, max_length=120)
    published_at: str | None = None
    effective_from: str | None = None
    effective_until: str | None = None
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    mime_type: str = Field(pattern=r"^(application/pdf|text/plain|text/markdown)$")
    byte_size: int = Field(gt=0, le=50 * 1024 * 1024)
    page_count: int | None = Field(default=None, ge=0)
    storage_key: str = Field(min_length=8, max_length=500)
    extraction_metadata: dict[str, Any] = Field(default_factory=dict)


class ReviewCreate(StrictModel):
    decision: str = Field(pattern=r"^(approved|rejected|superseded)$")
    reason: str = Field(min_length=1, max_length=2000)


class RetrieveRequest(StrictModel):
    query: str = Field(min_length=1, max_length=2000)
    subject_id: uuid.UUID | None = None
    topic_id: uuid.UUID | None = None
    limit: int = Field(default=5, ge=1, le=20)
    min_score: float = Field(default=0.0, ge=0.0, le=1.0)


def rrf_merge(lexical: list[dict[str, Any]], vector: list[dict[str, Any]], limit: int, k: int = 20, lexical_weight: float = 4.0) -> list[dict[str, Any]]:
    """Funde rankings sem somar scores incompatíveis, priorizando léxico jurídico."""
    merged: dict[uuid.UUID, dict[str, Any]] = {}
    for rank, row in enumerate(lexical, 1):
        item = merged.setdefault(row["id"], dict(row))
        item["lexical_rank"] = rank
        item["lexical_score"] = float(row.get("lexical_score", 0.0))
    for rank, row in enumerate(vector, 1):
        item = merged.setdefault(row["id"], dict(row))
        item["vector_rank"] = rank
        item["vector_score"] = float(row.get("vector_score", 0.0))
    for item in merged.values():
        item["rrf_score"] = (lexical_weight / (k + item.get("lexical_rank", 10_000))) + (1 / (k + item.get("vector_rank", 10_000)))
    return sorted(merged.values(), key=lambda row: (-row["rrf_score"], str(row["id"])))[:limit]


def _explicit_article_locator(query: str) -> str | None:
    """Extract a generic article reference as a deterministic lexical signal."""
    match = re.search(r"\bart(?:igo)?\.?\s*(\d+[ºo]?(?:\s*-\s*[A-Za-z])?)\b", query, re.I)
    if not match:
        return None
    number = re.sub(r"\s+", " ", match.group(1).strip())
    return f"Art. {number}"


def _embed(query: str, settings: Settings) -> tuple[list[float], str, str]:
    request = urllib.request.Request(
        f"{getattr(settings, 'embeddings_url', 'http://mentor-concursos-embeddings:8090')}/embed",
        data=json.dumps({"texts": [f"query: {query}"], "prefix": "query:"}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            body = json.loads(response.read(256 * 1024))
        vector = body["vectors"][0]
        if len(vector) != 384:
            raise ValueError("embedding_dimension_invalid")
        return vector, body["model_id"], body["revision"]
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=503, detail="Serviço de embeddings indisponível") from exc


@router.post("/sources", status_code=201)
def create_source(request: Request, body: SourceCreate, user: UserDep, settings: Annotated[Settings, Depends(get_settings)]) -> JSONResponse:
    def operation(connection: psycopg.Connection) -> tuple[int, dict[str, Any]]:
        row = connection.execute("INSERT INTO mentor_concursos.knowledge_sources(owner_user_id,source_type,title,issuer,authority,canonical_url,license_status,trust_level,subject_id,metadata) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *", (user.id, body.source_type, body.title, body.issuer, body.authority, body.canonical_url, body.license_status, body.trust_level, body.subject_id, json.dumps(body.metadata))).fetchone()
        _audit(connection, "user", "knowledge_source_created", "knowledge_sources", row["id"], request.state.request_id)
        return 201, _row_response(row)
    return _mutate(request, user, settings, body.model_dump(mode="json"), operation)


@router.get("/sources")
def list_sources(user: UserDep, settings: Annotated[Settings, Depends(get_settings)], limit: int = Query(50, ge=1, le=100)) -> dict[str, Any]:
    with _connect(settings) as connection:
        rows = connection.execute("SELECT * FROM mentor_concursos.knowledge_sources WHERE owner_user_id=%s ORDER BY created_at DESC,id LIMIT %s", (user.id, limit)).fetchall()
    return {"items": [_row_response(row) for row in rows], "next_cursor": None}


@router.get("/sources/{source_id}")
def get_source(source_id: uuid.UUID, user: UserDep, settings: Annotated[Settings, Depends(get_settings)]) -> dict[str, Any]:
    with _connect(settings) as connection:
        row = connection.execute("SELECT * FROM mentor_concursos.knowledge_sources WHERE id=%s AND owner_user_id=%s", (source_id, user.id)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Fonte não encontrada")
    return _row_response(row)


@router.post("/sources/{source_id}/versions", status_code=201)
def create_version(source_id: uuid.UUID, request: Request, body: VersionCreate, user: UserDep, settings: Annotated[Settings, Depends(get_settings)]) -> JSONResponse:
    def operation(connection: psycopg.Connection) -> tuple[int, dict[str, Any]]:
        if not connection.execute("SELECT 1 FROM mentor_concursos.knowledge_sources WHERE id=%s AND owner_user_id=%s", (source_id, user.id)).fetchone():
            raise HTTPException(status_code=404, detail="Fonte não encontrada")
        row = connection.execute("INSERT INTO mentor_concursos.knowledge_source_versions(source_id,version_label,published_at,effective_from,effective_until,sha256,mime_type,byte_size,page_count,storage_key,extraction_metadata) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *", (source_id, body.version_label, body.published_at, body.effective_from, body.effective_until, body.sha256, body.mime_type, body.byte_size, body.page_count, body.storage_key, json.dumps(body.extraction_metadata))).fetchone()
        _audit(connection, "user", "knowledge_version_created", "knowledge_source_versions", row["id"], request.state.request_id)
        return 201, _row_response(row)
    return _mutate(request, user, settings, body.model_dump(mode="json") | {"source_id": str(source_id)}, operation)


@router.post("/versions/{version_id}/ingest", status_code=202)
def request_ingest(version_id: uuid.UUID, request: Request, user: UserDep, settings: Annotated[Settings, Depends(get_settings)]) -> JSONResponse:
    def operation(connection: psycopg.Connection) -> tuple[int, dict[str, Any]]:
        if not connection.execute("SELECT 1 FROM mentor_concursos.knowledge_source_versions v JOIN mentor_concursos.knowledge_sources s ON s.id=v.source_id WHERE v.id=%s AND s.owner_user_id=%s", (version_id, user.id)).fetchone():
            raise HTTPException(status_code=404, detail="Versão não encontrada")
        key = request.headers["Idempotency-Key"]
        row = connection.execute("INSERT INTO mentor_concursos.ingestion_jobs(source_version_id,requested_by,idempotency_key) VALUES (%s,%s,%s) ON CONFLICT (source_version_id,idempotency_key) DO UPDATE SET updated_at=CURRENT_TIMESTAMP RETURNING *", (version_id, user.id, key)).fetchone()
        _audit(connection, "user", "knowledge_ingestion_requested", "ingestion_jobs", row["id"], request.state.request_id)
        return 202, _row_response(row)
    return _mutate(request, user, settings, {"version_id": str(version_id)}, operation)


@router.get("/jobs/{job_id}")
def get_job(job_id: uuid.UUID, user: UserDep, settings: Annotated[Settings, Depends(get_settings)]) -> dict[str, Any]:
    with _connect(settings) as connection:
        row = connection.execute("SELECT j.* FROM mentor_concursos.ingestion_jobs j WHERE j.id=%s AND j.requested_by=%s", (job_id, user.id)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Job não encontrado")
    return _row_response(row)


@router.post("/versions/{version_id}/review")
def review_version(version_id: uuid.UUID, request: Request, body: ReviewCreate, user: UserDep, settings: Annotated[Settings, Depends(get_settings)]) -> JSONResponse:
    def operation(connection: psycopg.Connection) -> tuple[int, dict[str, Any]]:
        row = connection.execute("SELECT v.*,s.owner_user_id,u.role FROM mentor_concursos.knowledge_source_versions v JOIN mentor_concursos.knowledge_sources s ON s.id=v.source_id JOIN mentor_concursos.users u ON u.id=%s WHERE v.id=%s AND s.owner_user_id=%s FOR UPDATE", (user.id, version_id, user.id)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Versão não encontrada")
        if row["role"] not in {"source_reviewer", "admin"}:
            raise HTTPException(status_code=403, detail="Permissão insuficiente")
        if body.decision == "approved" and row["status"] not in {"pending_review", "embedded", "indexed"}:
            raise HTTPException(status_code=409, detail="Versão não pronta para aprovação")
        new_status = body.decision if body.decision != "approved" else "indexed"
        connection.execute("UPDATE mentor_concursos.knowledge_source_versions SET status=%s WHERE id=%s", (new_status, version_id))
        review = connection.execute("INSERT INTO mentor_concursos.source_reviews(source_id,source_version_id,reviewer,decision,reason) VALUES (%s,%s,%s,%s,%s) RETURNING *", (row["source_id"], version_id, user.id, body.decision, body.reason)).fetchone()
        _audit(connection, "user", "knowledge_version_reviewed", "knowledge_source_versions", version_id, request.state.request_id, {"decision": body.decision})
        return 200, _row_response(review)
    return _mutate(request, user, settings, body.model_dump(mode="json") | {"version_id": str(version_id)}, operation)


@router.post("/retrieve")
def retrieve(request: Request, body: RetrieveRequest, user: UserDep, _: TokenDep, settings: Annotated[Settings, Depends(get_settings)]) -> dict[str, Any]:
    vector, model_id, revision = _embed(body.query, settings)
    vector_literal = "[" + ",".join(str(float(value)) for value in vector) + "]"
    filters = ["c.status='indexed'", "v.status='indexed'", "s.status='approved'", "s.owner_user_id=%s"]
    params: list[Any] = [user.id]
    if body.subject_id:
        filters.append("c.subject_id=%s")
        params.append(body.subject_id)
    if body.topic_id:
        filters.append("c.topic_id=%s")
        params.append(body.topic_id)
    where = " AND ".join(filters)
    with _connect(settings) as connection:
        common = """FROM mentor_concursos.knowledge_chunks c
            JOIN mentor_concursos.knowledge_source_versions v ON v.id=c.source_version_id
            JOIN mentor_concursos.knowledge_sources s ON s.id=v.source_id
            JOIN mentor_concursos.knowledge_embeddings e ON e.chunk_id=c.id"""
        explicit_locator = _explicit_article_locator(body.query)
        lexical_params: list[Any] = [body.query, *params, body.query]
        article_order = "1"
        if explicit_locator:
            article_order = "CASE WHEN regexp_replace(c.legal_locator, '\\.$', '')=%s THEN 0 ELSE 1 END"
            lexical_params.append(explicit_locator)
        lexical_params.append(body.limit * 4)
        lexical = connection.execute(
            f"SELECT c.id,c.text,c.normalized_text,c.ordinal,c.legal_locator,c.content_sha256,s.id AS source_id,v.id AS source_version_id,s.title AS source_title,v.version_label,ts_rank_cd(c.search_vector, websearch_to_tsquery('portuguese', replace(%s, ' ', ' OR '))) AS lexical_score {common} WHERE {where} AND c.search_vector @@ websearch_to_tsquery('portuguese', replace(%s, ' ', ' OR ')) ORDER BY {article_order},lexical_score DESC,c.id LIMIT %s",
            lexical_params,
        ).fetchall()
        vector_rows = connection.execute(
            f"SELECT c.id,c.text,c.normalized_text,c.ordinal,c.legal_locator,c.content_sha256,s.id AS source_id,v.id AS source_version_id,s.title AS source_title,v.version_label,1 - (e.embedding <=> %s::vector) AS vector_score {common} WHERE {where} ORDER BY vector_score DESC,c.id LIMIT %s",
            [vector_literal, *params, body.limit * 4],
        ).fetchall()
        # RRF evita somar scores de escalas diferentes. A calibração sintética
        # estratificada fixou k=20 e peso lexical 4.0; o desempate por UUID
        # torna o resultado estável.
        k = 20
        lexical_weight = 4.0
        returned = [row for row in rrf_merge(lexical, vector_rows, body.limit, k, lexical_weight)
                    if max(float(row.get("lexical_score") or 0), float(row.get("vector_score") or 0)) >= body.min_score]
        scores = [{"chunk_id": str(row["id"]), "rrf_score": row["rrf_score"], "lexical_rank": row.get("lexical_rank"), "vector_rank": row.get("vector_rank"), "lexical_score": row.get("lexical_score"), "vector_score": row.get("vector_score")} for row in returned]
        query_hash = hashlib.sha256(body.query.strip().lower().encode()).hexdigest()
        connection.execute("INSERT INTO mentor_concursos.retrieval_audit(user_id,query_hash,filters,returned_chunk_ids,scores,model_id,model_revision,request_id) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)", (user.id, query_hash, json.dumps({"subject_id": str(body.subject_id) if body.subject_id else None, "topic_id": str(body.topic_id) if body.topic_id else None, "rrf_k": k, "lexical_weight": lexical_weight}), [row["id"] for row in returned], json.dumps(scores), model_id, revision, request.state.request_id))
    return {"items": [_row_response(row) for row in returned], "model_id": model_id, "model_revision": revision, "fusion": {"method": "rrf", "k": k, "lexical_weight": lexical_weight}, "next_cursor": None}
