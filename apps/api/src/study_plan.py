"""API do planejador diário: proposta, confirmação e replanejamento seguro."""

# ruff: noqa: E501
from __future__ import annotations

import json
import uuid
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Annotated, Any, Literal
from zoneinfo import ZoneInfo

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import Field, model_validator

from .academic import (
    StrictModel,
    TokenDep,
    UserDep,
    _audit,
    _connect,
    _fingerprint,
    _mutate,
    _row_response,
)
from .config import Settings, get_settings
from .study_plan_engine import DEFAULT_SHARES, WEEKDAYS, PlanValidationError, build_plan

router = APIRouter(prefix="/api/v1/study", tags=["study-plan"])


class ProposalCreate(StrictModel):
    goal_id: uuid.UUID | None = None
    exam_id: uuid.UUID | None = None
    start_date: date | None = None
    end_date: date | None = None
    total_days: int | None = Field(default=None, ge=1, le=1826)
    timezone: str | None = Field(default=None, min_length=1, max_length=64)
    availability: dict[str, int]
    preferred_block_minutes: int = Field(default=60, ge=15, le=240)
    activity_shares: dict[str, int] = Field(default_factory=lambda: dict(DEFAULT_SHARES))
    reason: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def valid_scope_and_horizon(self) -> ProposalCreate:
        if bool(self.goal_id) == bool(self.exam_id):
            raise ValueError("Informe exatamente um objetivo ou concurso")
        if (self.end_date is None) == (self.total_days is None):
            raise ValueError("Informe exatamente uma data-limite ou quantidade de dias")
        return self


class LegacyStudyPlanCreate(StrictModel):
    exam_id: uuid.UUID
    deadline: date
    days_per_week: int = Field(ge=1, le=7)
    hours_per_day: int = Field(ge=1, le=16)


class ProposalAction(StrictModel):
    confirmation: Literal["confirmar", "confirmo", "sim, criar plano"] = "confirmar"


class ProposalCancel(StrictModel):
    cancel: Literal[True]


def plan_metrics(
    deadline: date, today: date, days_per_week: int, hours_per_day: int
) -> tuple[int, int]:
    days = (deadline - today).days
    if days <= 0:
        raise ValueError("deadline_must_be_future")
    return max(1, (days + 6) // 7), days_per_week * hours_per_day * 60


def distribute_minutes(weekly_minutes: int, disciplines: list[dict[str, Any]]) -> dict[str, int]:
    from .study_plan_engine import largest_remainder

    if len(disciplines) == 1 and not int(disciplines[0].get("weight") or 0):
        return {str(disciplines[0].get("subject")): 10}
    return largest_remainder(
        weekly_minutes,
        [(str(d.get("subject")), max(0, int(d.get("weight") or 0))) for d in disciplines],
    )


def review_schedule(weeks: int, study_weeks: list[int]) -> list[int]:
    return sorted(
        {
            week + interval
            for week in study_weeks
            for interval in (1, 3, 8)
            if week + interval < weeks
        }
    )


def _local_today(timezone: str) -> date:
    try:
        return datetime.now(ZoneInfo(timezone)).date()
    except Exception as exc:
        raise HTTPException(status_code=422, detail="Fuso horário inválido") from exc


def _json(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, date | datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json(item) for item in value]
    return value


def _profile(connection: psycopg.Connection, user_id: uuid.UUID) -> dict[str, Any]:
    return connection.execute(
        "SELECT timezone,available_minutes_per_day,level FROM mentor_concursos.users WHERE id=%s",
        (user_id,),
    ).fetchone()


def _scope(
    connection: psycopg.Connection, user_id: uuid.UUID, body: ProposalCreate
) -> tuple[dict[str, Any] | None, dict[str, Any], list[dict[str, Any]]]:
    goal = None
    if body.goal_id:
        goal = connection.execute(
            "SELECT * FROM mentor_concursos.study_goals WHERE id=%s AND user_id=%s",
            (body.goal_id, user_id),
        ).fetchone()
        if not goal:
            raise HTTPException(status_code=404, detail="Objetivo não encontrado")
        exam = (
            connection.execute(
                "SELECT * FROM mentor_concursos.exams WHERE id=%s", (goal["exam_id"],)
            ).fetchone()
            if goal["exam_id"]
            else None
        )
        subjects = connection.execute(
            "SELECT s.id AS subject_id,s.name,ss.weight,ss.priority,ss.ordinal,COALESCE(array_agg(st.topic_id ORDER BY t.ordinal) FILTER (WHERE st.status='included' AND t.id IS NOT NULL),ARRAY[]::uuid[]) AS topic_ids,COALESCE(max(tm.state),'not_started') AS mastery_state,COALESCE(max(tm.evidence_count),0) AS evidence_count,COALESCE((SELECT SUM(sess.net_duration_seconds) FROM mentor_concursos.study_sessions sess WHERE sess.user_id=%s AND sess.goal_id=sv.goal_id AND sess.subject_id=s.id AND sess.status='completed'),0) AS studied_seconds,COALESCE((SELECT COUNT(*) FROM mentor_concursos.study_plan_items pi JOIN mentor_concursos.study_cycles pc ON pc.id=pi.cycle_id WHERE pc.goal_id=sv.goal_id AND pi.subject_id=s.id AND pi.status='planned' AND pi.planned_for<CURRENT_DATE),0) AS overdue_items,COALESCE((SELECT ROUND(AVG(CASE WHEN pa.correct THEN 100 ELSE 0 END))::int FROM mentor_concursos.practice_attempts pa JOIN mentor_concursos.practice_questions pq ON pq.id=pa.question_id JOIN mentor_concursos.knowledge_source_versions kv ON kv.id=pq.source_version_id JOIN mentor_concursos.knowledge_sources ks ON ks.id=kv.source_id WHERE pa.user_id=%s AND ks.subject_id=s.id),50) AS accuracy_percent "
            "FROM mentor_concursos.syllabus_versions sv JOIN mentor_concursos.syllabus_subjects ss ON ss.syllabus_id=sv.id JOIN mentor_concursos.subjects s ON s.id=ss.subject_id LEFT JOIN mentor_concursos.syllabus_topics st ON st.syllabus_id=sv.id LEFT JOIN mentor_concursos.topics t ON t.id=st.topic_id AND t.subject_id=s.id LEFT JOIN mentor_concursos.topic_mastery tm ON tm.goal_id=sv.goal_id AND tm.user_id=%s AND tm.topic_id=t.id WHERE sv.goal_id=%s AND sv.status='active' GROUP BY sv.goal_id,s.id,s.name,ss.weight,ss.priority,ss.ordinal ORDER BY ss.ordinal,s.id",
            (user_id, user_id, user_id, goal["id"]),
        ).fetchall()
    else:
        exam = connection.execute(
            "SELECT * FROM mentor_concursos.exams WHERE id=%s", (body.exam_id,)
        ).fetchone()
        if not exam:
            raise HTTPException(status_code=404, detail="Concurso não encontrado")
        subjects = []
        for ordinal, item in enumerate((exam["metadata"] or {}).get("disciplines") or [], 1):
            subject = connection.execute(
                "SELECT id,name FROM mentor_concursos.subjects WHERE code=%s AND active",
                (item.get("subject"),),
            ).fetchone()
            if subject:
                topics = connection.execute(
                    "SELECT id FROM mentor_concursos.topics WHERE subject_id=%s AND active ORDER BY ordinal,id",
                    (subject["id"],),
                ).fetchall()
                subjects.append(
                    {
                        "subject_id": subject["id"],
                        "name": subject["name"],
                        "weight": item.get("weight") or 1,
                        "priority": item.get("priority") or "normal",
                        "ordinal": ordinal,
                        "topic_ids": [row["id"] for row in topics],
                        "mastery_state": "not_started",
                    }
                )
    if not subjects:
        raise HTTPException(status_code=422, detail="Objetivo ou edital sem disciplinas aplicáveis")
    return goal, exam or {}, [_json(row) for row in subjects]


def _calculate(
    connection: psycopg.Connection, user_id: uuid.UUID, body: ProposalCreate
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any] | None, dict[str, Any]]:
    profile = _profile(connection, user_id)
    timezone = body.timezone or profile["timezone"]
    start = body.start_date or _local_today(timezone)
    goal, exam, subjects = _scope(connection, user_id, body)
    normalized = _json(body.model_dump()) | {
        "start_date": start.isoformat(),
        "timezone": timezone,
        "subjects": subjects,
        "level": profile["level"],
    }
    try:
        summary = build_plan(
            start_date=start,
            end_date=body.end_date,
            total_days=body.total_days,
            timezone=timezone,
            availability=body.availability,
            preferred_block_minutes=body.preferred_block_minutes,
            shares=body.activity_shares,
            subjects=subjects,
        )
    except PlanValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return normalized, summary, goal, exam


def _create_proposal(
    request: Request, body: ProposalCreate, user: UserDep, settings: Settings, proposal_type: str
) -> JSONResponse:
    def operation(connection: psycopg.Connection) -> tuple[int, dict[str, Any]]:
        normalized, summary, goal, exam = _calculate(connection, user.id, body)
        connection.execute(
            "UPDATE mentor_concursos.study_plan_proposals SET status='expired' WHERE user_id=%s AND status='draft' AND expires_at<=CURRENT_TIMESTAMP",
            (user.id,),
        )
        if connection.execute(
            "SELECT 1 FROM mentor_concursos.study_plan_proposals WHERE user_id=%s AND status='draft' FOR UPDATE",
            (user.id,),
        ).fetchone():
            raise HTTPException(
                status_code=409,
                detail="Já existe uma proposta pendente; confirme ou cancele antes de criar outra",
            )
        fingerprint = _fingerprint(normalized)
        row = connection.execute(
            "INSERT INTO mentor_concursos.study_plan_proposals(user_id,goal_id,exam_id,proposal_type,normalized_payload,calculated_summary,fingerprint,expires_at) VALUES (%s,%s,%s,%s,%s,%s,%s,CURRENT_TIMESTAMP + interval '30 minutes') RETURNING *",
            (
                user.id,
                goal["id"] if goal else None,
                exam.get("id"),
                proposal_type,
                json.dumps(normalized),
                json.dumps(summary),
                fingerprint,
            ),
        ).fetchone()
        _audit(
            connection,
            "user",
            "study_plan_proposal_created",
            "study_plan_proposals",
            row["id"],
            request.state.request_id,
            {"type": proposal_type, "capacity_minutes": summary["total_capacity_minutes"]},
        )
        return 201, {
            "state": "awaiting_confirmation",
            "proposal": _row_response(row),
            "simulation": summary,
        }

    return _mutate(request, user, settings, body.model_dump(mode="json"), operation)


@router.post("/plan/proposals", status_code=201)
def create_proposal(
    request: Request,
    body: ProposalCreate,
    user: UserDep,
    _: TokenDep,
    settings: Annotated[Settings, Depends(get_settings)],
) -> JSONResponse:
    return _create_proposal(request, body, user, settings, "create")


@router.post("/plan/replan/proposals", status_code=201)
def create_replan_proposal(
    request: Request,
    body: ProposalCreate,
    user: UserDep,
    _: TokenDep,
    settings: Annotated[Settings, Depends(get_settings)],
) -> JSONResponse:
    if not body.goal_id:
        raise HTTPException(status_code=422, detail="Replanejamento exige objetivo existente")
    return _create_proposal(request, body, user, settings, "replan")


@router.get("/plan/proposals/current")
def current_proposal(
    user: UserDep, _: TokenDep, settings: Annotated[Settings, Depends(get_settings)]
) -> dict[str, Any]:
    with _connect(settings) as connection, connection.transaction():
        connection.execute(
            "UPDATE mentor_concursos.study_plan_proposals SET status='expired' WHERE user_id=%s AND status='draft' AND expires_at<=CURRENT_TIMESTAMP",
            (user.id,),
        )
        row = connection.execute(
            "SELECT * FROM mentor_concursos.study_plan_proposals WHERE user_id=%s AND status='draft' ORDER BY created_at DESC LIMIT 1",
            (user.id,),
        ).fetchone()
    return {"state": "pending", "proposal": _row_response(row)} if row else {"state": "none"}


def _persist_confirmed(
    connection: psycopg.Connection, proposal: dict[str, Any], user_id: uuid.UUID, request_id: str
) -> dict[str, Any]:
    payload = proposal["normalized_payload"]
    summary = proposal["calculated_summary"]
    goal_id = proposal["goal_id"]
    if goal_id is None:
        exam = connection.execute(
            "SELECT * FROM mentor_concursos.exams WHERE id=%s", (proposal["exam_id"],)
        ).fetchone()
        if connection.execute(
            "SELECT 1 FROM mentor_concursos.study_goals WHERE user_id=%s AND active FOR UPDATE",
            (user_id,),
        ).fetchone():
            raise HTTPException(
                status_code=409, detail="Já existe um plano ativo; use /plano ajustar"
            )
        goal = connection.execute(
            "INSERT INTO mentor_concursos.study_goals(user_id,exam_id,name,horizon,weekly_minutes,active,status) VALUES (%s,%s,%s,%s,%s,TRUE,'active') RETURNING *",
            (
                user_id,
                exam["id"],
                f"{exam['role']} — {exam['organization']}",
                f"até {summary['period']['end_date']}",
                summary["average_weekly_minutes"],
            ),
        ).fetchone()
        goal_id = goal["id"]
        syllabus = connection.execute(
            "INSERT INTO mentor_concursos.syllabus_versions(goal_id,version,title,source,status) VALUES (%s,1,%s,'cadastro existente','active') RETURNING id",
            (goal_id, f"Plano {exam['organization']} — {exam['role']}"),
        ).fetchone()
        for subject in payload["subjects"]:
            connection.execute(
                "INSERT INTO mentor_concursos.syllabus_subjects(syllabus_id,subject_id,weight,ordinal,priority) VALUES (%s,%s,%s,%s,%s)",
                (
                    syllabus["id"],
                    subject["subject_id"],
                    subject.get("weight") or 1,
                    subject["ordinal"],
                    subject.get("priority") or "normal",
                ),
            )
            for topic_id in subject.get("topic_ids") or []:
                connection.execute(
                    "INSERT INTO mentor_concursos.syllabus_topics(syllabus_id,topic_id,status) VALUES (%s,%s,'included') ON CONFLICT DO NOTHING",
                    (syllabus["id"], topic_id),
                )
    else:
        goal = connection.execute(
            "SELECT * FROM mentor_concursos.study_goals WHERE id=%s AND user_id=%s FOR UPDATE",
            (goal_id, user_id),
        ).fetchone()
        if not goal:
            raise HTTPException(status_code=404, detail="Objetivo não encontrado")
        if proposal["proposal_type"] == "replan":
            connection.execute(
                "UPDATE mentor_concursos.study_plan_items i SET status='cancelled' FROM mentor_concursos.study_cycles c WHERE i.cycle_id=c.id AND c.goal_id=%s AND i.status='planned' AND COALESCE(i.planned_for,CURRENT_DATE)>=CURRENT_DATE AND NOT EXISTS (SELECT 1 FROM mentor_concursos.study_sessions ss WHERE ss.plan_item_id=i.id AND ss.status IN ('active','paused'))",
                (goal_id,),
            )
        connection.execute(
            "UPDATE mentor_concursos.study_goals SET active=TRUE,status='active',weekly_minutes=%s,horizon=%s,version=version+1 WHERE id=%s",
            (summary["average_weekly_minutes"], f"até {summary['period']['end_date']}", goal_id),
        )
    revision = connection.execute(
        "SELECT COALESCE(MAX(plan_revision),0)+1 AS revision FROM mentor_concursos.study_cycles WHERE goal_id=%s",
        (goal_id,),
    ).fetchone()["revision"]
    cycles: dict[tuple[int, int], dict[str, Any]] = {}
    for item in summary["items"]:
        planned_for = date.fromisoformat(item["planned_for"])
        iso = planned_for.isocalendar()
        key = (iso.year, iso.week)
        if key not in cycles:
            monday = planned_for - timedelta(days=planned_for.weekday())
            sunday = monday + timedelta(days=6)
            weekly = sum(
                day["capacity_minutes"]
                for day in summary["calendar"]
                if monday <= date.fromisoformat(day["date"]) <= sunday
            )
            cycles[key] = connection.execute(
                "INSERT INTO mentor_concursos.study_cycles(goal_id,name,starts_at,ends_at,weekly_minutes,status,proposal_id,plan_revision) VALUES (%s,%s,%s,%s,%s,'draft',%s,%s) RETURNING *",
                (
                    goal_id,
                    f"Semana {iso.week}/{iso.year}",
                    datetime.combine(monday, time.min, UTC),
                    datetime.combine(sunday + timedelta(days=1), time.min, UTC),
                    max(1, weekly),
                    proposal["id"],
                    revision,
                ),
            ).fetchone()
        criteria = {
            "simulation": "Simulado",
            "questions": "Questões",
            "spaced_review": "Revisão espaçada",
            "new_content": "Conteúdo novo",
        }.get(item.get("activity_detail"), "")
        connection.execute(
            "INSERT INTO mentor_concursos.study_plan_items(cycle_id,subject_id,topic_id,activity_type,planned_minutes,ordinal,planned_for,completion_criteria,proposal_id) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                cycles[key]["id"],
                item["subject_id"],
                item["topic_id"],
                item["activity_type"],
                item["planned_minutes"],
                item["ordinal"],
                planned_for,
                criteria,
                proposal["id"],
            ),
        )
    for index, day in enumerate(WEEKDAYS):
        connection.execute(
            "INSERT INTO mentor_concursos.user_study_availability(user_id,weekday,available_minutes) VALUES (%s,%s,%s) ON CONFLICT (user_id,weekday) DO UPDATE SET available_minutes=EXCLUDED.available_minutes,active=TRUE,version=user_study_availability.version+1",
            (user_id, index, payload["availability"][day]),
        )
    connection.execute(
        "UPDATE mentor_concursos.study_plan_proposals SET status='confirmed',confirmed_at=CURRENT_TIMESTAMP,goal_id=%s,version=version+1 WHERE id=%s",
        (goal_id, proposal["id"]),
    )
    _audit(
        connection,
        "user",
        "study_plan_confirmed",
        "study_plan_proposals",
        proposal["id"],
        request_id,
        {"goal_id": str(goal_id), "revision": revision, "items": len(summary["items"])},
    )
    return {
        "state": "created",
        "goal_id": str(goal_id),
        "revision": revision,
        "period": summary["period"],
        "total_capacity_minutes": summary["total_capacity_minutes"],
        "plan_items": len(summary["items"]),
    }


@router.post("/plan/proposals/{proposal_id}/confirm")
def confirm_proposal(
    proposal_id: uuid.UUID,
    request: Request,
    body: ProposalAction,
    user: UserDep,
    _: TokenDep,
    settings: Annotated[Settings, Depends(get_settings)],
) -> JSONResponse:
    def operation(connection: psycopg.Connection) -> tuple[int, dict[str, Any]]:
        proposal = connection.execute(
            "SELECT * FROM mentor_concursos.study_plan_proposals WHERE id=%s AND user_id=%s FOR UPDATE",
            (proposal_id, user.id),
        ).fetchone()
        if not proposal:
            raise HTTPException(status_code=404, detail="Proposta não encontrada")
        if proposal["status"] == "confirmed":
            raise HTTPException(status_code=409, detail="Proposta já confirmada")
        if proposal["status"] != "draft":
            raise HTTPException(
                status_code=409, detail="Proposta não está disponível para confirmação"
            )
        if proposal["expires_at"] <= datetime.now(UTC):
            connection.execute(
                "UPDATE mentor_concursos.study_plan_proposals SET status='expired' WHERE id=%s",
                (proposal_id,),
            )
            raise HTTPException(
                status_code=409, detail="Proposta expirada; gere uma nova simulação"
            )
        payload = proposal["normalized_payload"]
        if _fingerprint(payload) != proposal["fingerprint"]:
            raise HTTPException(
                status_code=409, detail="Proposta inconsistente; gere uma nova simulação"
            )
        try:
            recalculated = build_plan(
                start_date=date.fromisoformat(payload["start_date"]),
                end_date=date.fromisoformat(payload["end_date"])
                if payload.get("end_date")
                else None,
                total_days=payload.get("total_days"),
                timezone=payload["timezone"],
                availability=payload["availability"],
                preferred_block_minutes=payload["preferred_block_minutes"],
                shares=payload["activity_shares"],
                subjects=payload["subjects"],
            )
        except (KeyError, TypeError, ValueError, PlanValidationError) as exc:
            raise HTTPException(
                status_code=409, detail="Proposta inconsistente; gere uma nova simulação"
            ) from exc
        if recalculated != proposal["calculated_summary"]:
            raise HTTPException(
                status_code=409, detail="Proposta inconsistente; gere uma nova simulação"
            )
        return 201, _persist_confirmed(connection, proposal, user.id, request.state.request_id)

    return _mutate(
        request, user, settings, {"proposal_id": str(proposal_id), **body.model_dump()}, operation
    )


@router.post("/plan/proposals/{proposal_id}/cancel")
def cancel_proposal(
    proposal_id: uuid.UUID,
    request: Request,
    body: ProposalCancel,
    user: UserDep,
    _: TokenDep,
    settings: Annotated[Settings, Depends(get_settings)],
) -> JSONResponse:
    def operation(connection: psycopg.Connection) -> tuple[int, dict[str, Any]]:
        row = connection.execute(
            "UPDATE mentor_concursos.study_plan_proposals SET status='cancelled',cancelled_at=CURRENT_TIMESTAMP,version=version+1 WHERE id=%s AND user_id=%s AND status='draft' RETURNING id",
            (proposal_id, user.id),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Proposta pendente não encontrada")
        _audit(
            connection,
            "user",
            "study_plan_proposal_cancelled",
            "study_plan_proposals",
            proposal_id,
            request.state.request_id,
        )
        return 200, {"state": "cancelled"}

    return _mutate(
        request, user, settings, {"proposal_id": str(proposal_id), **body.model_dump()}, operation
    )


def _plan_rows(
    connection: psycopg.Connection, user_id: uuid.UUID, start: date, end: date
) -> list[dict[str, Any]]:
    return connection.execute(
        "SELECT i.*,s.name AS subject_name,t.name AS topic_name FROM mentor_concursos.study_plan_items i JOIN mentor_concursos.study_cycles c ON c.id=i.cycle_id JOIN mentor_concursos.study_goals g ON g.id=c.goal_id JOIN mentor_concursos.subjects s ON s.id=i.subject_id LEFT JOIN mentor_concursos.topics t ON t.id=i.topic_id WHERE g.user_id=%s AND g.active AND i.planned_for BETWEEN %s AND %s AND i.status<>'cancelled' ORDER BY i.planned_for,i.ordinal",
        (user_id, start, end),
    ).fetchall()


@router.get("/plan/today")
def today_plan(
    user: UserDep, _: TokenDep, settings: Annotated[Settings, Depends(get_settings)]
) -> dict[str, Any]:
    with _connect(settings) as connection:
        profile = _profile(connection, user.id)
        today = _local_today(profile["timezone"])
        items = _plan_rows(connection, user.id, today, today)
        capacity = connection.execute(
            "SELECT available_minutes FROM mentor_concursos.user_study_availability WHERE user_id=%s AND weekday=%s AND active",
            (user.id, today.weekday()),
        ).fetchone()
    pending = next((row for row in items if row["status"] == "planned"), None)
    return {
        "date": today.isoformat(),
        "capacity_minutes": capacity["available_minutes"] if capacity else 0,
        "planned_minutes": sum(row["planned_minutes"] for row in items),
        "items": [_row_response(row) for row in items],
        "next_item": _row_response(pending) if pending else None,
    }


@router.get("/plan/week")
def week_plan(
    user: UserDep,
    _: TokenDep,
    settings: Annotated[Settings, Depends(get_settings)],
    offset: int = Query(0, ge=0, le=52),
) -> dict[str, Any]:
    with _connect(settings) as connection:
        profile = _profile(connection, user.id)
        today = _local_today(profile["timezone"])
        start = today - timedelta(days=today.weekday()) + timedelta(weeks=offset)
        end = start + timedelta(days=6)
        items = _plan_rows(connection, user.id, start, end)
    days = []
    for index in range(7):
        current = start + timedelta(days=index)
        rows = [row for row in items if row["planned_for"] == current]
        days.append(
            {
                "date": current.isoformat(),
                "planned_minutes": sum(row["planned_minutes"] for row in rows),
                "completed_minutes": sum(
                    row["planned_minutes"] for row in rows if row["status"] == "completed"
                ),
                "pending": sum(1 for row in rows if row["status"] == "planned"),
                "activities": sorted({row["activity_type"] for row in rows}),
            }
        )
    return {"period": {"start_date": start.isoformat(), "end_date": end.isoformat()}, "days": days}


@router.get("/plan/status")
def plan_status(
    user: UserDep, _: TokenDep, settings: Annotated[Settings, Depends(get_settings)]
) -> dict[str, Any]:
    with _connect(settings) as connection:
        goal = connection.execute(
            "SELECT * FROM mentor_concursos.study_goals WHERE user_id=%s AND active", (user.id,)
        ).fetchone()
        if not goal:
            return {"state": "no_active_plan"}
        stats = connection.execute(
            "SELECT COALESCE(SUM(i.planned_minutes),0) AS total,COALESCE(SUM(i.planned_minutes) FILTER (WHERE i.status='completed'),0) AS completed,COUNT(*) FILTER (WHERE i.status='planned' AND i.planned_for<CURRENT_DATE) AS overdue,MIN(i.planned_for) FILTER (WHERE i.activity_type='review' AND i.status='planned') AS next_review FROM mentor_concursos.study_plan_items i JOIN mentor_concursos.study_cycles c ON c.id=i.cycle_id WHERE c.goal_id=%s AND i.status<>'cancelled'",
            (goal["id"],),
        ).fetchone()
    total = int(stats["total"])
    completed = int(stats["completed"])
    return {
        "state": "active",
        "goal": _row_response(goal),
        "total_minutes": total,
        "completed_minutes": completed,
        "progress_percent": completed * 100 // total if total else 0,
        "overdue_items": stats["overdue"],
        "next_review": _json(stats["next_review"]),
        "needs_adjustment": bool(stats["overdue"]),
    }


@router.get("/next-item")
def next_item(
    user: UserDep, _: TokenDep, settings: Annotated[Settings, Depends(get_settings)]
) -> dict[str, Any]:
    with _connect(settings) as connection:
        row = connection.execute(
            "SELECT i.*,s.name AS subject_name,t.name AS topic_name FROM mentor_concursos.study_plan_items i JOIN mentor_concursos.study_cycles c ON c.id=i.cycle_id JOIN mentor_concursos.study_goals g ON g.id=c.goal_id JOIN mentor_concursos.subjects s ON s.id=i.subject_id LEFT JOIN mentor_concursos.topics t ON t.id=i.topic_id WHERE g.user_id=%s AND g.active AND i.status='planned' ORDER BY i.planned_for NULLS LAST,i.ordinal LIMIT 1",
            (user.id,),
        ).fetchone()
    return {"state": "pending", "item": _row_response(row)} if row else {"state": "no_pending_item"}


@router.post("/plan", status_code=201)
def legacy_plan(
    request: Request,
    body: LegacyStudyPlanCreate,
    user: UserDep,
    _: TokenDep,
    settings: Annotated[Settings, Depends(get_settings)],
) -> JSONResponse:
    availability = {
        day: body.hours_per_day * 60 if index < body.days_per_week else 0
        for index, day in enumerate(WEEKDAYS)
    }
    modern = ProposalCreate(exam_id=body.exam_id, end_date=body.deadline, availability=availability)
    return _create_proposal(request, modern, user, settings, "create")
