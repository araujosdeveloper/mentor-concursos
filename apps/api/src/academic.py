"""Domínio acadêmico determinístico e API versionada.

Não há chamadas de modelo, ingestão ou regras inferidas neste módulo: toda
transição é validada no servidor e persistida no PostgreSQL.
"""

# ruff: noqa: E501

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Annotated, Any, TypeVar

import psycopg
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from psycopg.rows import dict_row
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .auth import require_service_token, signed_context_user_id
from .config import Settings, get_settings

router = APIRouter(prefix="/api/v1", tags=["academic"])
T = TypeVar("T")


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ProfilePatch(StrictModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    timezone: str | None = Field(default=None, min_length=1, max_length=64)
    available_minutes_per_day: int | None = Field(default=None, ge=1, le=1440)
    level: str | None = Field(default=None, pattern=r"^(beginner|intermediate|advanced)$")


class GoalCreate(StrictModel):
    name: str = Field(min_length=1, max_length=200)
    horizon: str = Field(min_length=1, max_length=120)
    weekly_minutes: int = Field(ge=1, le=10080)
    exam_id: uuid.UUID | None = None
    track_codes: list[str] = Field(default_factory=list, max_length=4)


class GoalPatch(StrictModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    horizon: str | None = Field(default=None, min_length=1, max_length=120)
    weekly_minutes: int | None = Field(default=None, ge=1, le=10080)
    version: int = Field(ge=1)


class SyllabusCreate(StrictModel):
    version: int = Field(gt=0)
    title: str = Field(min_length=1, max_length=240)
    source: str = Field(min_length=1, max_length=500)
    published_at: date | None = None
    checksum: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


class SyllabusSubjectCreate(StrictModel):
    subject_id: uuid.UUID
    weight: float | None = Field(default=None, ge=0)
    ordinal: int = Field(gt=0)
    priority: str = Field(default="normal", pattern=r"^(low|normal|high)$")
    metadata: dict[str, Any] = Field(default_factory=dict)


class SyllabusTopicCreate(StrictModel):
    topic_id: uuid.UUID
    incidence: float | None = Field(default=None, ge=0)
    status: str = Field(default="included", pattern=r"^(included|excluded|unknown)$")


class CycleCreate(StrictModel):
    name: str = Field(min_length=1, max_length=200)
    starts_at: datetime
    ends_at: datetime
    weekly_minutes: int = Field(gt=0, le=10080)

    @field_validator("ends_at")
    @classmethod
    def end_after_start(cls, value: datetime, info):  # type: ignore[no-untyped-def]
        start = info.data.get("starts_at")
        if start and value <= start:
            raise ValueError("ends_at deve ser posterior a starts_at")
        return value


class PlanItemCreate(StrictModel):
    subject_id: uuid.UUID
    topic_id: uuid.UUID | None = None
    activity_type: str = Field(pattern=r"^(study|review|revision|exercise)$")
    planned_minutes: int = Field(gt=0, le=1440)
    ordinal: int = Field(gt=0)
    planned_for: date | None = None
    completion_criteria: str = Field(default="", max_length=500)


class SessionStart(StrictModel):
    goal_id: uuid.UUID
    subject_id: uuid.UUID
    topic_id: uuid.UUID | None = None
    plan_item_id: uuid.UUID | None = None
    started_at: datetime | None = None
    observation: str | None = Field(default=None, max_length=1000)


class SessionObservation(StrictModel):
    version: int = Field(ge=1)
    at: datetime | None = None
    observation: str | None = Field(default=None, max_length=1000)


@dataclass(frozen=True)
class AcademicUser:
    id: uuid.UUID
    telegram_user_id: int
    name: str


def _connect(settings: Settings) -> psycopg.Connection:
    return psycopg.connect(
        host=settings.database_host,
        port=settings.database_port,
        dbname=settings.database_name,
        user=settings.database_user,
        password=settings.database_password,
        row_factory=dict_row,
    )


def _utc(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _session_timestamp(value: datetime | None) -> datetime:
    """Normalize a client timestamp and reject future observations."""
    normalized = _utc(value)
    if normalized > datetime.now(UTC):
        raise HTTPException(status_code=422, detail="Timestamp futuro não permitido")
    return normalized


def _jsonable(value: Any) -> Any:
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    return value


def _db_error(error: psycopg.Error) -> HTTPException:
    if getattr(error, "sqlstate", None) in {"23505", "23P01"}:
        return HTTPException(status_code=409, detail="Conflito de estado")
    if getattr(error, "sqlstate", None) == "23503":
        return HTTPException(status_code=422, detail="Referência inválida")
    return HTTPException(status_code=409, detail="Operação não aplicável")


def _user_dependency(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    _: Annotated[None, Depends(require_service_token)],
    telegram_user_id: Annotated[int | None, Header(alias="X-Telegram-User-ID")] = None,
) -> AcademicUser:
    signed_id = signed_context_user_id(request, settings)
    if signed_id is not None:
        telegram_user_id = signed_id
    if telegram_user_id is None:
        raise HTTPException(status_code=401, detail="Usuário não identificado")
    with _connect(settings) as connection:
        row = connection.execute(
            "SELECT id, telegram_user_id, name FROM mentor_concursos.users WHERE telegram_user_id = %s AND status = 'active'",
            (telegram_user_id,),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    return AcademicUser(uuid.UUID(str(row["id"])), int(row["telegram_user_id"]), row["name"])


UserDep = Annotated[AcademicUser, Depends(_user_dependency)]
TokenDep = Annotated[None, Depends(require_service_token)]


def _idempotency_key(key: str | None) -> str:
    if not key or not 8 <= len(key) <= 128 or not all(c.isalnum() or c in "._:-" for c in key):
        raise HTTPException(status_code=422, detail="Idempotency-Key obrigatório e inválido")
    return key


def _fingerprint(payload: Any) -> str:
    return hashlib.sha256(json.dumps(_jsonable(payload), sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _idempotency_scope(request: Request, user: AcademicUser) -> str:
    return f"{request.method}:{request.url.path}:{user.id}"


def _begin_idempotency(connection: psycopg.Connection, key: str, scope: str, fingerprint: str) -> dict[str, Any] | None:
    row = connection.execute(
        "SELECT fingerprint, status, response FROM mentor_concursos.idempotency_keys WHERE key=%s AND scope=%s FOR UPDATE",
        (key, scope),
    ).fetchone()
    if row:
        if row["fingerprint"] != fingerprint:
            raise HTTPException(status_code=409, detail="Idempotency-Key reutilizado com requisição diferente")
        if row["status"] == "completed":
            return row["response"]
        raise HTTPException(status_code=409, detail="Operação idempotente em processamento")
    connection.execute(
        "INSERT INTO mentor_concursos.idempotency_keys(key,scope,fingerprint,status,expires_at) VALUES (%s,%s,%s,'processing',CURRENT_TIMESTAMP + interval '24 hours')",
        (key, scope, fingerprint),
    )
    return None


def _finish_idempotency(connection: psycopg.Connection, key: str, scope: str, code: int, response: dict[str, Any]) -> None:
    envelope = {"_status_code": code, "_body": response}
    connection.execute(
        "UPDATE mentor_concursos.idempotency_keys SET status='completed', response=%s WHERE key=%s AND scope=%s",
        (json.dumps(_jsonable(envelope)), key, scope),
    )


def _audit(connection: psycopg.Connection, actor: str, action: str, entity: str, entity_id: uuid.UUID | None, request_id: str, metadata: dict[str, Any] | None = None) -> None:
    connection.execute(
        "INSERT INTO mentor_concursos.audit_events(actor,action,entity,entity_id,request_id,metadata) VALUES (%s,%s,%s,%s,%s,%s)",
        (actor, action, entity, entity_id, request_id, json.dumps(_jsonable(metadata or {}))),
    )


def _mutate(request: Request, user: AcademicUser, settings: Settings, payload: Any, operation: Callable[[psycopg.Connection], tuple[int, dict[str, Any]]]) -> JSONResponse:
    key = _idempotency_key(request.headers.get("Idempotency-Key"))
    # A chave é isolada por operação e usuário; nunca pode replayar a resposta
    # de outro usuário autenticado com o mesmo valor.
    scope = _idempotency_scope(request, user)
    fingerprint = _fingerprint(payload)
    request_id = getattr(request.state, "request_id", "unknown")
    try:
        with _connect(settings) as connection, connection.transaction():
                replay = _begin_idempotency(connection, key, scope, fingerprint)
                if replay is not None:
                    if isinstance(replay, dict) and "_body" in replay:
                        return JSONResponse(
                            status_code=int(replay.get("_status_code", 200)),
                            content=_jsonable(replay["_body"]),
                            headers={"X-Request-ID": request_id},
                        )
                    return JSONResponse(status_code=200, content=_jsonable(replay), headers={"X-Request-ID": request_id})
                code, response = operation(connection)
                _finish_idempotency(connection, key, scope, code, response)
                return JSONResponse(status_code=code, content=_jsonable(response), headers={"X-Request-ID": request_id})
    except psycopg.Error as error:
        raise _db_error(error) from None


def _row_response(row: dict[str, Any]) -> dict[str, Any]:
    return {k: _jsonable(v) for k, v in row.items()}


@router.get("/users/me")
def get_profile(user: UserDep, settings: Annotated[Settings, Depends(get_settings)]) -> dict[str, Any]:
    with _connect(settings) as connection:
        row = connection.execute("SELECT * FROM mentor_concursos.users WHERE id=%s", (user.id,)).fetchone()
    return _row_response(row)


@router.patch("/users/me")
def patch_profile(request: Request, body: ProfilePatch, user: UserDep, settings: Annotated[Settings, Depends(get_settings)]) -> JSONResponse:
    values = body.model_dump(exclude_none=True)
    if not values:
        raise HTTPException(status_code=422, detail="Nenhum campo para atualizar")
    def operation(connection: psycopg.Connection) -> tuple[int, dict[str, Any]]:
        sets = ", ".join(f"{key}=%s" for key in values)
        row = connection.execute(f"UPDATE mentor_concursos.users SET {sets} WHERE id=%s RETURNING *", (*values.values(), user.id)).fetchone()
        _audit(connection, "user", "profile_updated", "users", user.id, request.state.request_id)
        return 200, _row_response(row)
    return _mutate(request, user, settings, values, operation)


@router.get("/study-tracks")
def list_tracks(_: TokenDep, settings: Annotated[Settings, Depends(get_settings)]) -> dict[str, Any]:
    with _connect(settings) as connection:
        rows = connection.execute("SELECT * FROM mentor_concursos.study_tracks WHERE active ORDER BY code").fetchall()
    return {"items": [_row_response(row) for row in rows], "next_cursor": None}


@router.get("/subjects")
def list_subjects(_: TokenDep, settings: Annotated[Settings, Depends(get_settings)], limit: int = Query(50, ge=1, le=100)) -> dict[str, Any]:
    with _connect(settings) as connection:
        rows = connection.execute("SELECT * FROM mentor_concursos.subjects WHERE active ORDER BY name LIMIT %s", (limit,)).fetchall()
    return {"items": [_row_response(row) for row in rows], "next_cursor": None}


@router.get("/exams")
def list_exams(_: TokenDep, settings: Annotated[Settings, Depends(get_settings)]) -> dict[str, Any]:
    with _connect(settings) as connection:
        rows = connection.execute("SELECT * FROM mentor_concursos.exams ORDER BY organization, role").fetchall()
    return {"items": [_row_response(row) for row in rows], "next_cursor": None}


@router.get("/subjects/{subject_id}/topics")
def list_topics(subject_id: uuid.UUID, _: TokenDep, settings: Annotated[Settings, Depends(get_settings)]) -> dict[str, Any]:
    with _connect(settings) as connection:
        rows = connection.execute("SELECT * FROM mentor_concursos.topics WHERE subject_id=%s AND active ORDER BY path, ordinal", (subject_id,)).fetchall()
    return {"items": [_row_response(row) for row in rows], "next_cursor": None}


@router.post("/goals", status_code=201)
def create_goal(request: Request, body: GoalCreate, user: UserDep, settings: Annotated[Settings, Depends(get_settings)]) -> JSONResponse:
    def operation(connection: psycopg.Connection) -> tuple[int, dict[str, Any]]:
        row = connection.execute("INSERT INTO mentor_concursos.study_goals(user_id,exam_id,name,horizon,weekly_minutes) VALUES (%s,%s,%s,%s,%s) RETURNING *", (user.id, body.exam_id, body.name, body.horizon, body.weekly_minutes)).fetchone()
        for code in body.track_codes:
            track = connection.execute("SELECT id FROM mentor_concursos.study_tracks WHERE code=%s AND active", (code,)).fetchone()
            if not track:
                raise HTTPException(status_code=422, detail="Trilha inválida")
            connection.execute("INSERT INTO mentor_concursos.goal_tracks(goal_id,track_id) VALUES (%s,%s)", (row["id"], track["id"]))
        _audit(connection, "user", "goal_created", "study_goals", row["id"], request.state.request_id)
        return 201, _row_response(row)
    return _mutate(request, user, settings, body.model_dump(mode="json"), operation)


@router.get("/goals")
def list_goals(user: UserDep, settings: Annotated[Settings, Depends(get_settings)], limit: int = Query(50, ge=1, le=100)) -> dict[str, Any]:
    with _connect(settings) as connection:
        rows = connection.execute("SELECT * FROM mentor_concursos.study_goals WHERE user_id=%s ORDER BY created_at DESC LIMIT %s", (user.id, limit)).fetchall()
    return {"items": [_row_response(row) for row in rows], "next_cursor": None}


@router.get("/goals/{goal_id}")
def get_goal(goal_id: uuid.UUID, user: UserDep, settings: Annotated[Settings, Depends(get_settings)]) -> dict[str, Any]:
    with _connect(settings) as connection:
        row = connection.execute("SELECT * FROM mentor_concursos.study_goals WHERE id=%s AND user_id=%s", (goal_id, user.id)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Objetivo não encontrado")
    return _row_response(row)


@router.patch("/goals/{goal_id}")
def patch_goal(goal_id: uuid.UUID, request: Request, body: GoalPatch, user: UserDep, settings: Annotated[Settings, Depends(get_settings)]) -> JSONResponse:
    values = body.model_dump(exclude={"version"}, exclude_none=True)
    def operation(connection: psycopg.Connection) -> tuple[int, dict[str, Any]]:
        if not values:
            raise HTTPException(status_code=422, detail="Nenhum campo para atualizar")
        sets = ", ".join(f"{key}=%s" for key in values)
        row = connection.execute(f"UPDATE mentor_concursos.study_goals SET {sets}, version=version+1 WHERE id=%s AND user_id=%s AND version=%s RETURNING *", (*values.values(), goal_id, user.id, body.version)).fetchone()
        if not row:
            raise HTTPException(status_code=409, detail="Versão do objetivo desatualizada")
        _audit(connection, "user", "goal_updated", "study_goals", goal_id, request.state.request_id)
        return 200, _row_response(row)
    return _mutate(request, user, settings, body.model_dump(mode="json"), operation)


@router.post("/goals/{goal_id}/activate")
def activate_goal(goal_id: uuid.UUID, request: Request, user: UserDep, settings: Annotated[Settings, Depends(get_settings)]) -> JSONResponse:
    def operation(connection: psycopg.Connection) -> tuple[int, dict[str, Any]]:
        row = connection.execute("UPDATE mentor_concursos.study_goals SET active=TRUE,status='active',version=version+1 WHERE id=%s AND user_id=%s RETURNING *", (goal_id, user.id)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Objetivo não encontrado")
        _audit(connection, "user", "goal_activated", "study_goals", goal_id, request.state.request_id)
        return 200, _row_response(row)
    return _mutate(request, user, settings, {"goal_id": str(goal_id)}, operation)


@router.post("/goals/{goal_id}/syllabi", status_code=201)
def create_syllabus(goal_id: uuid.UUID, request: Request, body: SyllabusCreate, user: UserDep, settings: Annotated[Settings, Depends(get_settings)]) -> JSONResponse:
    def operation(connection: psycopg.Connection) -> tuple[int, dict[str, Any]]:
        if not connection.execute("SELECT 1 FROM mentor_concursos.study_goals WHERE id=%s AND user_id=%s", (goal_id, user.id)).fetchone():
            raise HTTPException(status_code=404, detail="Objetivo não encontrado")
        row = connection.execute("INSERT INTO mentor_concursos.syllabus_versions(goal_id,version,title,source,published_at,checksum) VALUES (%s,%s,%s,%s,%s,%s) RETURNING *", (goal_id, body.version, body.title, body.source, body.published_at, body.checksum)).fetchone()
        _audit(connection, "user", "syllabus_created", "syllabus_versions", row["id"], request.state.request_id)
        return 201, _row_response(row)
    return _mutate(request, user, settings, body.model_dump(mode="json"), operation)


@router.get("/goals/{goal_id}/syllabi")
def list_syllabi(goal_id: uuid.UUID, user: UserDep, settings: Annotated[Settings, Depends(get_settings)]) -> dict[str, Any]:
    with _connect(settings) as connection:
        rows = connection.execute("SELECT s.* FROM mentor_concursos.syllabus_versions s JOIN mentor_concursos.study_goals g ON g.id=s.goal_id WHERE s.goal_id=%s AND g.user_id=%s ORDER BY s.version DESC", (goal_id, user.id)).fetchall()
    return {"items": [_row_response(row) for row in rows], "next_cursor": None}


@router.post("/syllabi/{syllabus_id}/activate")
def activate_syllabus(syllabus_id: uuid.UUID, request: Request, user: UserDep, settings: Annotated[Settings, Depends(get_settings)]) -> JSONResponse:
    def operation(connection: psycopg.Connection) -> tuple[int, dict[str, Any]]:
        row = connection.execute("SELECT s.* FROM mentor_concursos.syllabus_versions s JOIN mentor_concursos.study_goals g ON g.id=s.goal_id WHERE s.id=%s AND g.user_id=%s FOR UPDATE", (syllabus_id, user.id)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Edital não encontrado")
        connection.execute("UPDATE mentor_concursos.syllabus_versions SET status='superseded' WHERE goal_id=%s AND status='active' AND id<>%s", (row["goal_id"], syllabus_id))
        row = connection.execute("UPDATE mentor_concursos.syllabus_versions SET status='active' WHERE id=%s RETURNING *", (syllabus_id,)).fetchone()
        _audit(connection, "user", "syllabus_activated", "syllabus_versions", syllabus_id, request.state.request_id)
        return 200, _row_response(row)
    return _mutate(request, user, settings, {"syllabus_id": str(syllabus_id)}, operation)


@router.post("/syllabi/{syllabus_id}/subjects", status_code=201)
def add_syllabus_subject(syllabus_id: uuid.UUID, request: Request, body: SyllabusSubjectCreate, user: UserDep, settings: Annotated[Settings, Depends(get_settings)]) -> JSONResponse:
    def operation(connection: psycopg.Connection) -> tuple[int, dict[str, Any]]:
        valid = connection.execute("SELECT 1 FROM mentor_concursos.syllabus_versions s JOIN mentor_concursos.study_goals g ON g.id=s.goal_id WHERE s.id=%s AND g.user_id=%s", (syllabus_id, user.id)).fetchone()
        if not valid:
            raise HTTPException(status_code=404, detail="Edital não encontrado")
        row = connection.execute("INSERT INTO mentor_concursos.syllabus_subjects(syllabus_id,subject_id,weight,ordinal,priority,metadata) VALUES (%s,%s,%s,%s,%s,%s) RETURNING *", (syllabus_id, body.subject_id, body.weight, body.ordinal, body.priority, json.dumps(body.metadata))).fetchone()
        _audit(connection, "user", "syllabus_subject_added", "syllabus_versions", syllabus_id, request.state.request_id)
        return 201, _row_response(row)
    return _mutate(request, user, settings, body.model_dump(mode="json"), operation)


@router.post("/syllabi/{syllabus_id}/topics", status_code=201)
def add_syllabus_topic(syllabus_id: uuid.UUID, request: Request, body: SyllabusTopicCreate, user: UserDep, settings: Annotated[Settings, Depends(get_settings)]) -> JSONResponse:
    def operation(connection: psycopg.Connection) -> tuple[int, dict[str, Any]]:
        valid = connection.execute("SELECT 1 FROM mentor_concursos.syllabus_versions s JOIN mentor_concursos.study_goals g ON g.id=s.goal_id WHERE s.id=%s AND g.user_id=%s", (syllabus_id, user.id)).fetchone()
        if not valid:
            raise HTTPException(status_code=404, detail="Edital não encontrado")
        row = connection.execute("INSERT INTO mentor_concursos.syllabus_topics(syllabus_id,topic_id,incidence,status) VALUES (%s,%s,%s,%s) RETURNING *", (syllabus_id, body.topic_id, body.incidence, body.status)).fetchone()
        _audit(connection, "user", "syllabus_topic_added", "syllabus_versions", syllabus_id, request.state.request_id)
        return 201, _row_response(row)
    return _mutate(request, user, settings, body.model_dump(mode="json"), operation)


@router.post("/goals/{goal_id}/cycles", status_code=201)
def create_cycle(goal_id: uuid.UUID, request: Request, body: CycleCreate, user: UserDep, settings: Annotated[Settings, Depends(get_settings)]) -> JSONResponse:
    def operation(connection: psycopg.Connection) -> tuple[int, dict[str, Any]]:
        if not connection.execute("SELECT 1 FROM mentor_concursos.study_goals WHERE id=%s AND user_id=%s", (goal_id, user.id)).fetchone():
            raise HTTPException(status_code=404, detail="Objetivo não encontrado")
        row = connection.execute("INSERT INTO mentor_concursos.study_cycles(goal_id,name,starts_at,ends_at,weekly_minutes) VALUES (%s,%s,%s,%s,%s) RETURNING *", (goal_id, body.name, _utc(body.starts_at), _utc(body.ends_at), body.weekly_minutes)).fetchone()
        _audit(connection, "user", "cycle_created", "study_cycles", row["id"], request.state.request_id)
        return 201, _row_response(row)
    return _mutate(request, user, settings, body.model_dump(mode="json"), operation)


@router.get("/goals/{goal_id}/cycles")
def list_cycles(goal_id: uuid.UUID, user: UserDep, settings: Annotated[Settings, Depends(get_settings)]) -> dict[str, Any]:
    with _connect(settings) as connection:
        rows = connection.execute("SELECT c.* FROM mentor_concursos.study_cycles c JOIN mentor_concursos.study_goals g ON g.id=c.goal_id WHERE c.goal_id=%s AND g.user_id=%s ORDER BY c.starts_at DESC", (goal_id, user.id)).fetchall()
    return {"items": [_row_response(row) for row in rows], "next_cursor": None}


@router.post("/cycles/{cycle_id}/activate")
def activate_cycle(cycle_id: uuid.UUID, request: Request, user: UserDep, settings: Annotated[Settings, Depends(get_settings)]) -> JSONResponse:
    def operation(connection: psycopg.Connection) -> tuple[int, dict[str, Any]]:
        row = connection.execute("SELECT c.* FROM mentor_concursos.study_cycles c JOIN mentor_concursos.study_goals g ON g.id=c.goal_id WHERE c.id=%s AND g.user_id=%s FOR UPDATE", (cycle_id, user.id)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Ciclo não encontrado")
        connection.execute("UPDATE mentor_concursos.study_cycles SET status='paused' WHERE goal_id=%s AND status='active' AND id<>%s", (row["goal_id"], cycle_id))
        row = connection.execute("UPDATE mentor_concursos.study_cycles SET status='active',version=version+1 WHERE id=%s RETURNING *", (cycle_id,)).fetchone()
        _audit(connection, "user", "cycle_activated", "study_cycles", cycle_id, request.state.request_id)
        return 200, _row_response(row)
    return _mutate(request, user, settings, {"cycle_id": str(cycle_id)}, operation)


@router.post("/cycles/{cycle_id}/items", status_code=201)
def add_cycle_item(cycle_id: uuid.UUID, request: Request, body: PlanItemCreate, user: UserDep, settings: Annotated[Settings, Depends(get_settings)]) -> JSONResponse:
    def operation(connection: psycopg.Connection) -> tuple[int, dict[str, Any]]:
        valid = connection.execute("SELECT c.goal_id FROM mentor_concursos.study_cycles c JOIN mentor_concursos.study_goals g ON g.id=c.goal_id WHERE c.id=%s AND g.user_id=%s", (cycle_id, user.id)).fetchone()
        if not valid:
            raise HTTPException(status_code=404, detail="Ciclo não encontrado")
        subject = connection.execute("SELECT 1 FROM mentor_concursos.subjects WHERE id=%s AND active", (body.subject_id,)).fetchone()
        if not subject:
            raise HTTPException(status_code=422, detail="Disciplina inválida")
        if body.topic_id is not None and not connection.execute("SELECT 1 FROM mentor_concursos.topics WHERE id=%s AND subject_id=%s AND active", (body.topic_id, body.subject_id)).fetchone():
            raise HTTPException(status_code=422, detail="Tópico inválido para a disciplina")
        row = connection.execute("INSERT INTO mentor_concursos.study_plan_items(cycle_id,subject_id,topic_id,activity_type,planned_minutes,ordinal,planned_for,completion_criteria) VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *", (cycle_id, body.subject_id, body.topic_id, body.activity_type, body.planned_minutes, body.ordinal, body.planned_for, body.completion_criteria)).fetchone()
        _audit(connection, "user", "cycle_item_added", "study_plan_items", row["id"], request.state.request_id)
        return 201, _row_response(row)
    return _mutate(request, user, settings, body.model_dump(mode="json"), operation)


@router.get("/cycles/{cycle_id}/items")
def list_cycle_items(cycle_id: uuid.UUID, user: UserDep, settings: Annotated[Settings, Depends(get_settings)]) -> dict[str, Any]:
    with _connect(settings) as connection:
        rows = connection.execute("SELECT i.* FROM mentor_concursos.study_plan_items i JOIN mentor_concursos.study_cycles c ON c.id=i.cycle_id JOIN mentor_concursos.study_goals g ON g.id=c.goal_id WHERE i.cycle_id=%s AND g.user_id=%s ORDER BY i.ordinal", (cycle_id, user.id)).fetchall()
    return {"items": [_row_response(row) for row in rows], "next_cursor": None}


def _session_get(connection: psycopg.Connection, session_id: uuid.UUID, user_id: uuid.UUID, lock: bool = True) -> dict[str, Any] | None:
    suffix = " FOR UPDATE" if lock else ""
    return connection.execute(f"SELECT * FROM mentor_concursos.study_sessions WHERE id=%s AND user_id=%s{suffix}", (session_id, user_id)).fetchone()


def _session_update(connection: psycopg.Connection, session: dict[str, Any], status_value: str, at: datetime, observation: str | None = None) -> dict[str, Any]:
    if at < session["started_at"]:
        raise HTTPException(status_code=422, detail="Timestamp inválido")
    if status_value in {"completed", "cancelled"}:
        open_pause = connection.execute("SELECT started_at FROM mentor_concursos.study_session_pauses WHERE session_id=%s AND ended_at IS NULL FOR UPDATE", (session["id"],)).fetchone()
        pause_seconds = session["accumulated_pause_seconds"]
        if open_pause:
            pause_seconds += max(0, int((at - open_pause["started_at"]).total_seconds()))
            connection.execute("UPDATE mentor_concursos.study_session_pauses SET ended_at=%s WHERE session_id=%s AND ended_at IS NULL", (at, session["id"]))
        net = max(0, int((at - session["started_at"]).total_seconds()) - pause_seconds)
        row = connection.execute("UPDATE mentor_concursos.study_sessions SET status=%s,ended_at=%s,accumulated_pause_seconds=%s,net_duration_seconds=%s,version=version+1,observation=COALESCE(%s,observation) WHERE id=%s RETURNING *", (status_value, at, pause_seconds, net, observation, session["id"])).fetchone()
    else:
        row = connection.execute("UPDATE mentor_concursos.study_sessions SET status=%s,version=version+1,observation=COALESCE(%s,observation) WHERE id=%s RETURNING *", (status_value, observation, session["id"])).fetchone()
    return row


@router.post("/sessions/start", status_code=201)
def start_session(request: Request, body: SessionStart, user: UserDep, settings: Annotated[Settings, Depends(get_settings)]) -> JSONResponse:
    def operation(connection: psycopg.Connection) -> tuple[int, dict[str, Any]]:
        now = _session_timestamp(body.started_at)
        if connection.execute("SELECT 1 FROM mentor_concursos.study_sessions WHERE user_id=%s AND status IN ('active','paused')", (user.id,)).fetchone():
            raise HTTPException(status_code=409, detail="Usuário já possui sessão aberta")
        goal = connection.execute("SELECT 1 FROM mentor_concursos.study_goals WHERE id=%s AND user_id=%s", (body.goal_id, user.id)).fetchone()
        if not goal:
            raise HTTPException(status_code=404, detail="Objetivo não encontrado")
        if not connection.execute("SELECT 1 FROM mentor_concursos.subjects WHERE id=%s AND active", (body.subject_id,)).fetchone():
            raise HTTPException(status_code=422, detail="Disciplina inválida")
        if body.topic_id is not None and not connection.execute("SELECT 1 FROM mentor_concursos.topics WHERE id=%s AND subject_id=%s AND active", (body.topic_id, body.subject_id)).fetchone():
            raise HTTPException(status_code=422, detail="Tópico inválido para a disciplina")
        if body.plan_item_id is not None and not connection.execute("SELECT 1 FROM mentor_concursos.study_plan_items i JOIN mentor_concursos.study_cycles c ON c.id=i.cycle_id WHERE i.id=%s AND c.goal_id=%s AND i.subject_id=%s AND (i.topic_id IS NOT DISTINCT FROM %s)", (body.plan_item_id, body.goal_id, body.subject_id, body.topic_id)).fetchone():
            raise HTTPException(status_code=422, detail="Item de plano incompatível")
        row = connection.execute("INSERT INTO mentor_concursos.study_sessions(user_id,goal_id,plan_item_id,subject_id,topic_id,started_at,observation) VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING *", (user.id, body.goal_id, body.plan_item_id, body.subject_id, body.topic_id, now, body.observation)).fetchone()
        if body.plan_item_id is not None:
            connection.execute("UPDATE mentor_concursos.study_plan_items SET status='in_progress', updated_at=CURRENT_TIMESTAMP WHERE id=%s", (body.plan_item_id,))
        _audit(connection, "user", "session_started", "study_sessions", row["id"], request.state.request_id)
        return 201, _row_response(row)
    return _mutate(request, user, settings, body.model_dump(mode="json"), operation)


def _transition(session_id: uuid.UUID, request: Request, body: SessionObservation, user: AcademicUser, settings: Settings, target: str) -> JSONResponse:
    def operation(connection: psycopg.Connection) -> tuple[int, dict[str, Any]]:
        row = _session_get(connection, session_id, user.id)
        if not row:
            raise HTTPException(status_code=404, detail="Sessão não encontrada")
        if row["version"] != body.version:
            raise HTTPException(status_code=409, detail="Versão da sessão desatualizada")
        allowed = {"pause": ("active", "paused"), "resume": ("paused", "active"), "complete": ("active", "paused"), "cancel": ("active", "paused")}
        if row["status"] not in allowed[target]:
            raise HTTPException(status_code=409, detail="Transição de sessão inválida")
        at = _session_timestamp(body.at)
        if target == "pause":
            connection.execute("INSERT INTO mentor_concursos.study_session_pauses(session_id,started_at) VALUES (%s,%s)", (session_id, at))
            updated = _session_update(connection, row, "paused", at, body.observation)
        elif target == "resume":
            pause = connection.execute("SELECT * FROM mentor_concursos.study_session_pauses WHERE session_id=%s AND ended_at IS NULL FOR UPDATE", (session_id,)).fetchone()
            if not pause or at < pause["started_at"]:
                raise HTTPException(status_code=422, detail="Pausa inconsistente")
            connection.execute("UPDATE mentor_concursos.study_session_pauses SET ended_at=%s WHERE id=%s", (at, pause["id"]))
            row["accumulated_pause_seconds"] += int((at - pause["started_at"]).total_seconds())
            updated = connection.execute("UPDATE mentor_concursos.study_sessions SET status='active',accumulated_pause_seconds=%s,version=version+1,observation=COALESCE(%s,observation) WHERE id=%s RETURNING *", (row["accumulated_pause_seconds"], body.observation, session_id)).fetchone()
        else:
            updated = _session_update(connection, row, "completed" if target == "complete" else "cancelled", at, body.observation)
            if row["plan_item_id"] is not None:
                item_status = "completed" if target == "complete" else "planned"
                connection.execute("UPDATE mentor_concursos.study_plan_items SET status=%s, updated_at=CURRENT_TIMESTAMP WHERE id=%s", (item_status, row["plan_item_id"]))
        _audit(connection, "user", f"session_{target}d", "study_sessions", session_id, request.state.request_id)
        return 200, _row_response(updated)
    return _mutate(request, user, settings, body.model_dump(mode="json") | {"session_id": str(session_id), "target": target}, operation)


@router.post("/sessions/{session_id}/pause")
def pause_session(session_id: uuid.UUID, request: Request, body: SessionObservation, user: UserDep, settings: Annotated[Settings, Depends(get_settings)]) -> JSONResponse:
    return _transition(session_id, request, body, user, settings, "pause")


@router.post("/sessions/{session_id}/resume")
def resume_session(session_id: uuid.UUID, request: Request, body: SessionObservation, user: UserDep, settings: Annotated[Settings, Depends(get_settings)]) -> JSONResponse:
    return _transition(session_id, request, body, user, settings, "resume")


@router.post("/sessions/{session_id}/complete")
def complete_session(session_id: uuid.UUID, request: Request, body: SessionObservation, user: UserDep, settings: Annotated[Settings, Depends(get_settings)]) -> JSONResponse:
    return _transition(session_id, request, body, user, settings, "complete")


@router.post("/sessions/{session_id}/cancel")
def cancel_session(session_id: uuid.UUID, request: Request, body: SessionObservation, user: UserDep, settings: Annotated[Settings, Depends(get_settings)]) -> JSONResponse:
    return _transition(session_id, request, body, user, settings, "cancel")


@router.get("/sessions/current")
def current_session(user: UserDep, settings: Annotated[Settings, Depends(get_settings)]) -> dict[str, Any] | None:
    with _connect(settings) as connection:
        row = connection.execute("SELECT * FROM mentor_concursos.study_sessions WHERE user_id=%s AND status IN ('active','paused')", (user.id,)).fetchone()
    return _row_response(row) if row else None


@router.get("/sessions")
def list_sessions(user: UserDep, settings: Annotated[Settings, Depends(get_settings)], limit: int = Query(50, ge=1, le=100)) -> dict[str, Any]:
    with _connect(settings) as connection:
        rows = connection.execute("SELECT * FROM mentor_concursos.study_sessions WHERE user_id=%s ORDER BY started_at DESC LIMIT %s", (user.id, limit)).fetchall()
    return {"items": [_row_response(row) for row in rows], "next_cursor": None}


@router.get("/sessions/{session_id}")
def get_session(session_id: uuid.UUID, user: UserDep, settings: Annotated[Settings, Depends(get_settings)]) -> dict[str, Any]:
    with _connect(settings) as connection:
        row = _session_get(connection, session_id, user.id, lock=False)
    if not row:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")
    return _row_response(row)


@router.get("/goals/{goal_id}/progress")
def goal_progress(goal_id: uuid.UUID, user: UserDep, settings: Annotated[Settings, Depends(get_settings)]) -> dict[str, Any]:
    with _connect(settings) as connection:
        valid = connection.execute("SELECT 1 FROM mentor_concursos.study_goals WHERE id=%s AND user_id=%s", (goal_id, user.id)).fetchone()
        if not valid:
            raise HTTPException(status_code=404, detail="Objetivo não encontrado")
        row = connection.execute("SELECT COUNT(*) FILTER (WHERE status='completed') AS completed, COUNT(*) AS total, COALESCE(SUM(net_duration_seconds),0) AS net_seconds FROM mentor_concursos.study_sessions WHERE goal_id=%s AND user_id=%s", (goal_id, user.id)).fetchone()
        subjects = connection.execute("SELECT s.name, COALESCE(SUM(ss.net_duration_seconds),0) AS seconds FROM mentor_concursos.subjects s LEFT JOIN mentor_concursos.study_sessions ss ON ss.subject_id=s.id AND ss.goal_id=%s AND ss.user_id=%s AND ss.status='completed' GROUP BY s.name HAVING COALESCE(SUM(ss.net_duration_seconds),0) > 0 ORDER BY seconds DESC", (goal_id, user.id)).fetchall()
    return {"goal_id": str(goal_id), "completed_sessions": row["completed"], "total_sessions": row["total"], "net_duration_seconds": row["net_seconds"], "subjects": [{"name": s["name"], "minutes": round(int(s["seconds"]) / 60)} for s in subjects]}


@router.get("/goals/{goal_id}/topics/mastery")
def goal_mastery(goal_id: uuid.UUID, user: UserDep, settings: Annotated[Settings, Depends(get_settings)]) -> dict[str, Any]:
    with _connect(settings) as connection:
        rows = connection.execute("SELECT m.* FROM mentor_concursos.topic_mastery m WHERE m.goal_id=%s AND m.user_id=%s ORDER BY m.updated_at DESC", (goal_id, user.id)).fetchall()
    return {"items": [_row_response(row) for row in rows], "next_cursor": None}
