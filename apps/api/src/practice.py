"""Questões fundamentadas e revisão espaçada determinística."""

# ruff: noqa: E501

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from .academic import StrictModel, TokenDep, UserDep, _connect, _mutate, _row_response
from .config import Settings, get_settings

router = APIRouter(prefix="/api/v1/practice", tags=["practice"])


class QuestionRequest(StrictModel):
    subject_id: uuid.UUID | None = None


class AnswerRequest(StrictModel):
    question_id: uuid.UUID
    option: str


class SimulationRequest(StrictModel):
    quantity: int


def _citation(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_name": row["source_title"],
        "locator": row["legal_locator"],
        "source_version_id": str(row["source_version_id"]),
        "chunk_id": str(row["chunk_id"]),
        "hash": row["content_sha256"],
        "official_url": row["canonical_url"],
    }


def review_interval_days(correct: bool, consecutive_correct: int) -> int:
    if not correct:
        return 1
    return {1: 3, 2: 7, 3: 15}.get(consecutive_correct, 30)


def _indexed_chunks(connection: Any, user_id: uuid.UUID, subject_id: uuid.UUID | None, limit: int) -> list[dict[str, Any]]:
    filters = ["c.status='indexed'", "v.status='indexed'", "s.status='approved'", "s.owner_user_id=%s"]
    params: list[Any] = [user_id]
    if subject_id:
        filters.append("c.subject_id=%s")
        params.append(subject_id)
    params.append(limit)
    return list(connection.execute(f"""SELECT c.id chunk_id,c.text,c.legal_locator,c.content_sha256,
        c.source_version_id,s.title source_title,s.canonical_url
        FROM mentor_concursos.knowledge_chunks c
        JOIN mentor_concursos.knowledge_source_versions v ON v.id=c.source_version_id
        JOIN mentor_concursos.knowledge_sources s ON s.id=v.source_id
        WHERE {' AND '.join(filters)} ORDER BY md5(c.id::text || %s::text), c.id LIMIT %s""", [*params[:-1], str(user_id), params[-1]]).fetchall())


def _question_payload(row: dict[str, Any], alternatives: list[dict[str, str]], question_id: uuid.UUID) -> dict[str, Any]:
    return {
        "id": str(question_id),
        "prompt": f"Segundo a fonte indexada, qual alternativa corresponde ao dispositivo {row['legal_locator']}?",
        "alternatives": alternatives,
        "citation": _citation(row),
    }


@router.post("/question", status_code=201)
def create_question(request: Request, body: QuestionRequest, user: UserDep, settings: Annotated[Settings, Depends(get_settings)]) -> JSONResponse:
    def operation(connection: Any) -> tuple[int, dict[str, Any]]:
        rows = _indexed_chunks(connection, user.id, body.subject_id, 4)
        if len(rows) < 4:
            raise HTTPException(status_code=409, detail="Evidência insuficiente para criar questão")
        correct = rows[0]
        alternatives = [{"option": chr(65 + index), "text": row["text"][:500]} for index, row in enumerate(rows)]
        question_id = uuid.uuid4()
        prompt = f"Segundo a fonte indexada, qual alternativa corresponde ao dispositivo {correct['legal_locator']}?"
        citation = _citation(correct)
        connection.execute("""INSERT INTO mentor_concursos.practice_questions
            (id,owner_user_id,source_version_id,prompt,alternatives,correct_option,explanation,citation)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""", (question_id, user.id, correct["source_version_id"], prompt,
            json.dumps(alternatives, ensure_ascii=False), "A", "A alternativa correta reproduz o trecho indexado indicado na citação.", json.dumps(citation)))
        result = _question_payload(correct, alternatives, question_id)
        return 201, result
    return _mutate(request, user, settings, body.model_dump(mode="json"), operation)


@router.post("/answer")
def answer_question(request: Request, body: AnswerRequest, user: UserDep, settings: Annotated[Settings, Depends(get_settings)]) -> JSONResponse:
    option = body.option.strip().upper()
    if option not in {"A", "B", "C", "D", "E"}:
        raise HTTPException(status_code=422, detail="Alternativa inválida")

    def operation(connection: Any) -> tuple[int, dict[str, Any]]:
        question = connection.execute("""SELECT q.*,s.title source_title,s.canonical_url,c.legal_locator,c.content_sha256,c.id chunk_id
            FROM mentor_concursos.practice_questions q
            JOIN mentor_concursos.knowledge_source_versions v ON v.id=q.source_version_id
            JOIN mentor_concursos.knowledge_sources s ON s.id=v.source_id
            JOIN mentor_concursos.knowledge_chunks c ON c.source_version_id=v.id AND c.content_sha256=(q.citation->>'hash')
            WHERE q.id=%s AND q.owner_user_id=%s AND q.status='active' AND v.status='indexed' AND s.status='approved'
            FOR UPDATE""", (body.question_id, user.id)).fetchone()
        if not question:
            raise HTTPException(status_code=404, detail="Questão não encontrada")
        correct = option == question["correct_option"]
        now = datetime.now(UTC)
        connection.execute("""INSERT INTO mentor_concursos.practice_attempts
            (question_id,user_id,selected_option,correct,idempotency_key,request_id)
            VALUES (%s,%s,%s,%s,%s,%s)""", (body.question_id, user.id, option, correct,
            request.headers["Idempotency-Key"], request.state.request_id))
        review = connection.execute("SELECT * FROM mentor_concursos.practice_review_items WHERE user_id=%s AND question_id=%s FOR UPDATE", (user.id, body.question_id)).fetchone()
        consecutive = int(review["consecutive_correct"]) + 1 if review and correct else (0 if not correct else 1)
        interval = review_interval_days(correct, consecutive)
        connection.execute("""INSERT INTO mentor_concursos.practice_review_items
            (user_id,question_id,next_review_at,interval_days,consecutive_correct,attempt_count,last_correct)
            VALUES (%s,%s,%s,%s,%s,1,%s)
            ON CONFLICT (user_id,question_id) DO UPDATE SET next_review_at=EXCLUDED.next_review_at,
            interval_days=EXCLUDED.interval_days, consecutive_correct=EXCLUDED.consecutive_correct,
            attempt_count=mentor_concursos.practice_review_items.attempt_count+1,
            last_correct=EXCLUDED.last_correct,status='pending',updated_at=CURRENT_TIMESTAMP""",
            (user.id, body.question_id, now + timedelta(days=interval), interval, consecutive, correct))
        if correct:
            connection.execute("UPDATE mentor_concursos.practice_error_book SET resolved_at=%s WHERE user_id=%s AND question_id=%s AND resolved_at IS NULL", (now, user.id, body.question_id))
        else:
            connection.execute("""INSERT INTO mentor_concursos.practice_error_book(user_id,question_id)
                VALUES (%s,%s) ON CONFLICT (user_id,question_id) DO UPDATE SET wrong_count=practice_error_book.wrong_count+1,last_wrong_at=CURRENT_TIMESTAMP,resolved_at=NULL""", (user.id, body.question_id))
        citation = json.loads(question["citation"] if isinstance(question["citation"], str) else json.dumps(question["citation"]))
        return 200, {"question_id": str(body.question_id), "correct": correct, "selected_option": option,
            "correct_option": question["correct_option"], "explanation": question["explanation"], "citation": citation,
            "next_review_at": (now + timedelta(days=interval)).isoformat()}
    return _mutate(request, user, settings, body.model_dump(mode="json"), operation)


@router.post("/simulation", status_code=201)
def create_simulation(request: Request, body: SimulationRequest, user: UserDep, settings: Annotated[Settings, Depends(get_settings)]) -> JSONResponse:
    if not 1 <= body.quantity <= 20:
        raise HTTPException(status_code=422, detail="Quantidade deve estar entre 1 e 20")
    def operation(connection: Any) -> tuple[int, dict[str, Any]]:
        rows = _indexed_chunks(connection, user.id, None, body.quantity * 4)
        if len(rows) < body.quantity * 4:
            raise HTTPException(status_code=409, detail="Evidência insuficiente para o simulado")
        ids: list[uuid.UUID] = []
        for offset in range(body.quantity):
            correct = rows[offset * 4]
            alternatives = [{"option": chr(65 + i), "text": rows[offset * 4 + i]["text"][:500]} for i in range(4)]
            qid = uuid.uuid4()
            connection.execute("""INSERT INTO mentor_concursos.practice_questions
                (id,owner_user_id,source_version_id,prompt,alternatives,correct_option,explanation,citation)
                VALUES (%s,%s,%s,%s,%s,'A',%s,%s)""", (qid, user.id, correct["source_version_id"],
                f"Segundo a fonte indexada, qual alternativa corresponde ao dispositivo {correct['legal_locator']}?",
                json.dumps(alternatives, ensure_ascii=False), "A alternativa correta reproduz o trecho indexado indicado na citação.", json.dumps(_citation(correct))))
            ids.append(qid)
        run = connection.execute("INSERT INTO mentor_concursos.practice_runs(user_id,quantity,question_ids) VALUES (%s,%s,%s) RETURNING *", (user.id, body.quantity, ids)).fetchone()
        return 201, {"id": str(run["id"]), "quantity": body.quantity, "status": run["status"], "question_ids": [str(i) for i in ids]}
    return _mutate(request, user, settings, body.model_dump(mode="json"), operation)


@router.get("/reviews/next")
def next_review(user: UserDep, _: TokenDep, settings: Annotated[Settings, Depends(get_settings)]) -> dict[str, Any]:
    with _connect(settings) as connection:
        row = connection.execute("""SELECT r.*,q.prompt,q.alternatives,q.citation,q.id question_id
            FROM mentor_concursos.practice_review_items r JOIN mentor_concursos.practice_questions q ON q.id=r.question_id
            WHERE r.user_id=%s AND r.status='pending' AND r.next_review_at<=CURRENT_TIMESTAMP ORDER BY r.next_review_at,r.id LIMIT 1""", (user.id,)).fetchone()
    return _row_response(row) if row else {"item": None}


@router.get("/errors")
def error_book(user: UserDep, _: TokenDep, settings: Annotated[Settings, Depends(get_settings)]) -> dict[str, Any]:
    with _connect(settings) as connection:
        rows = connection.execute("""SELECT e.question_id,e.wrong_count,e.last_wrong_at,e.resolved_at,q.prompt,q.citation
            FROM mentor_concursos.practice_error_book e JOIN mentor_concursos.practice_questions q ON q.id=e.question_id
            WHERE e.user_id=%s ORDER BY e.resolved_at NULLS FIRST,e.wrong_count DESC,e.last_wrong_at DESC LIMIT 50""", (user.id,)).fetchall()
    return {"items": [_row_response(row) for row in rows]}


@router.get("/performance")
def performance(user: UserDep, _: TokenDep, settings: Annotated[Settings, Depends(get_settings)]) -> dict[str, Any]:
    with _connect(settings) as connection:
        row = connection.execute("SELECT COUNT(*) total,COUNT(*) FILTER (WHERE correct) correct,COUNT(*) FILTER (WHERE NOT correct) wrong FROM mentor_concursos.practice_attempts WHERE user_id=%s", (user.id,)).fetchone()
    total = int(row["total"])
    return {"total": total, "correct": int(row["correct"]), "wrong": int(row["wrong"]), "percentage": round((int(row["correct"]) / total) * 100, 2) if total else 0.0}


@router.post("/cancel")
def cancel_practice(request: Request, user: UserDep, settings: Annotated[Settings, Depends(get_settings)]) -> JSONResponse:
    def operation(connection: Any) -> tuple[int, dict[str, Any]]:
        row = connection.execute("UPDATE mentor_concursos.practice_runs SET status='cancelled' WHERE user_id=%s AND status='active' RETURNING id", (user.id,)).fetchone()
        return 200, {"state": "cancelled" if row else "nothing_to_cancel"}
    return _mutate(request, user, settings, {"cancel": True}, operation)
