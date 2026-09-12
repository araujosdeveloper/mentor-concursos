"""Geração determinística de plano de estudo a partir do edital e da disponibilidade."""

# ruff: noqa: E501

from __future__ import annotations

import math
import uuid
from datetime import UTC, date, datetime, time, timedelta
from typing import Annotated, Any

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import Field

from .academic import StrictModel, TokenDep, UserDep, _audit, _mutate, _row_response
from .config import Settings, get_settings

router = APIRouter(prefix="/api/v1/study", tags=["study-plan"])


class StudyPlanCreate(StrictModel):
    exam_id: uuid.UUID
    deadline: date
    days_per_week: int = Field(ge=1, le=7)
    hours_per_day: int = Field(ge=1, le=16)


def _day_start(value: date) -> datetime:
    return datetime.combine(value, time.min, tzinfo=UTC)


def plan_metrics(deadline: date, today: date, days_per_week: int, hours_per_day: int) -> tuple[int, int]:
    """Retorna (semanas, minutos_semanais) para o plano."""
    days = (deadline - today).days
    if days <= 0:
        raise ValueError("deadline_must_be_future")
    weekly_minutes = days_per_week * hours_per_day * 60
    weeks = max(1, math.ceil(days / 7))
    return weeks, weekly_minutes


def distribute_minutes(weekly_minutes: int, disciplines: list[dict[str, Any]]) -> dict[str, int]:
    """Distribui os minutos semanais entre as disciplinas proporcionalmente ao peso."""
    total_weight = sum(float(d.get("weight") or 0) for d in disciplines) or 1.0
    result: dict[str, int] = {}
    for discipline in disciplines:
        minutes = max(10, round(weekly_minutes * float(discipline.get("weight") or 0) / total_weight))
        result[str(discipline.get("subject"))] = minutes
    return result


@router.post("/plan", status_code=201)
def create_study_plan(
    request: Request,
    body: StudyPlanCreate,
    user: UserDep,
    _: TokenDep,
    settings: Annotated[Settings, Depends(get_settings)],
) -> JSONResponse:
    def operation(connection: psycopg.Connection) -> tuple[int, dict[str, Any]]:
        exam = connection.execute(
            "SELECT * FROM mentor_concursos.exams WHERE id=%s", (body.exam_id,)
        ).fetchone()
        if not exam:
            raise HTTPException(status_code=404, detail="Concurso não encontrado")
        disciplines = (exam["metadata"] or {}).get("disciplines") or []
        if not disciplines:
            raise HTTPException(status_code=422, detail="Edital sem disciplinas mapeadas")

        days = (body.deadline - date.today()).days
        if days <= 0:
            raise HTTPException(status_code=422, detail="Prazo deve ser no futuro")
        weeks, weekly_minutes = plan_metrics(body.deadline, date.today(), body.days_per_week, body.hours_per_day)
        allocation = distribute_minutes(weekly_minutes, disciplines)

        goal = connection.execute(
            "INSERT INTO mentor_concursos.study_goals(user_id,exam_id,name,horizon,weekly_minutes,active,status) "
            "VALUES (%s,%s,%s,%s,%s,TRUE,'active') RETURNING *",
            (
                user.id,
                body.exam_id,
                f"{exam['role']} — {exam['organization']}",
                f"até {body.deadline.isoformat()}",
                weekly_minutes,
            ),
        ).fetchone()
        _audit(connection, "user", "goal_created", "study_goals", goal["id"], request.state.request_id)

        syllabus = connection.execute(
            "INSERT INTO mentor_concursos.syllabus_versions(goal_id,version,title,source,published_at,status) "
            "VALUES (%s,1,%s,%s,%s,'active') RETURNING *",
            (goal["id"], f"Edital {exam['organization']} — {exam['role']}", "conteúdo programático", body.deadline),
        ).fetchone()
        _audit(connection, "user", "syllabus_created", "syllabus_versions", syllabus["id"], request.state.request_id)

        subject_ids: dict[str, uuid.UUID] = {}
        for index, discipline in enumerate(disciplines, start=1):
            subject = connection.execute(
                "SELECT id FROM mentor_concursos.subjects WHERE code=%s AND active",
                (discipline.get("subject"),),
            ).fetchone()
            if not subject:
                continue
            subject_ids[str(discipline.get("subject"))] = subject["id"]
            connection.execute(
                "INSERT INTO mentor_concursos.syllabus_subjects(syllabus_id,subject_id,weight,ordinal) "
                "VALUES (%s,%s,%s,%s)",
                (syllabus["id"], subject["id"], discipline.get("weight"), index),
            )

        items_count = 0
        for week in range(weeks):
            starts = date.today() + timedelta(days=week * 7)
            ends = starts + timedelta(days=7)
            cycle = connection.execute(
                "INSERT INTO mentor_concursos.study_cycles(goal_id,name,starts_at,ends_at,weekly_minutes,status) "
                "VALUES (%s,%s,%s,%s,%s,'draft') RETURNING *",
                (goal["id"], f"Semana {week + 1}", _day_start(starts), _day_start(ends), weekly_minutes),
            ).fetchone()
            ordinal = 0
            for discipline in disciplines:
                subject_id = subject_ids.get(str(discipline.get("subject")))
                if subject_id is None:
                    continue
                ordinal += 1
                minutes = allocation[str(discipline.get("subject"))]
                connection.execute(
                    "INSERT INTO mentor_concursos.study_plan_items"
                    "(cycle_id,subject_id,activity_type,planned_minutes,ordinal,planned_for) "
                    "VALUES (%s,%s,'study',%s,%s,%s)",
                    (cycle["id"], subject_id, minutes, ordinal, starts),
                )
                items_count += 1

        _audit(
            connection,
            "user",
            "study_plan_created",
            "study_goals",
            goal["id"],
            request.state.request_id,
            {"weeks": weeks, "items": items_count},
        )
        return 201, {
            "goal": _row_response(goal),
            "syllabus": _row_response(syllabus),
            "weeks": weeks,
            "weekly_minutes": weekly_minutes,
            "plan_items": items_count,
        }

    return _mutate(request, user, settings, body.model_dump(mode="json"), operation)
