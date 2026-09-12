"""Resposta fundamentada por consulta externa ao vivo a fontes oficiais (ADR-020)."""

# ruff: noqa: E501

from __future__ import annotations

import json
import re
import urllib.request
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import Field

from .academic import StrictModel, TokenDep, UserDep
from .config import Settings, get_settings

router = APIRouter(prefix="/api/v1/external", tags=["external"])

_INJECTION = re.compile(r"ignore\s+(all|previous)\s+instructions|system\s+prompt|reveal\s+hidden", re.I)


class ExternalAnswerRequest(StrictModel):
    query: str = Field(min_length=1, max_length=2000)
    category: str | None = None
    segment: str | None = None
    max_results: int = Field(default=5, ge=1, le=10)


def _call_external(settings: Settings, body: ExternalAnswerRequest) -> list[dict[str, Any]]:
    request = urllib.request.Request(
        f"{settings.external_url}/query",
        data=json.dumps(
            {
                "query": body.query,
                "category": body.category,
                "segment": body.segment,
                "max_results": body.max_results,
            }
        ).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            payload = json.loads(response.read(1024 * 1024))
        return list(payload.get("evidence", []))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=503, detail="Serviço de consulta externa indisponível") from exc


@router.post("/answer")
def answer(
    request: Request,
    body: ExternalAnswerRequest,
    user: UserDep,
    _: TokenDep,
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, Any]:
    if _INJECTION.search(body.query):
        return {
            "state": "insufficient_evidence",
            "answer": "A pergunta não contém uma solicitação acadêmica fundamentável em fontes oficiais.",
            "citations": [],
            "request_id": request.state.request_id,
        }
    try:
        evidence = _call_external(settings, body)
    except HTTPException:
        return {
            "state": "retrieval_failed",
            "answer": "Não foi possível consultar as fontes oficiais com segurança.",
            "citations": [],
            "request_id": request.state.request_id,
        }
    if not evidence:
        return {
            "state": "insufficient_evidence",
            "answer": "As fontes oficiais consultadas não ofereceram evidência suficiente para responder com segurança.",
            "citations": [],
            "request_id": request.state.request_id,
        }
    citations = [
        {
            "source_name": item.get("source_name"),
            "locator": item.get("locator"),
            "url": item.get("url"),
            "content_hash": item.get("content_hash"),
            "source_date": item.get("source_date"),
        }
        for item in evidence[:3]
    ]
    snippets = [item.get("snippet", "")[:2400] for item in evidence[:3]]
    return {
        "state": "answered",
        "answer": "\n\n".join(snippets),
        "citations": citations,
        "request_id": request.state.request_id,
    }
