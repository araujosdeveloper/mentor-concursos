"""Helpers de verificação de fundamentação do antigo RAG local.

A rota `/api/v1/rag/answer` foi aposentada (ADR-020): a resposta passa a ser
produzida por consulta externa ao vivo (`apps.api.src.external`). Este módulo
mantém apenas funções puras de verificação usadas em testes de regressão.
"""

# ruff: noqa: E501

from __future__ import annotations

import re
from typing import Any


def _injection(query: str) -> bool:
    return bool(re.search(r"ignore\s+(all|previous)\s+instructions|system\s+prompt|reveal\s+hidden", query, re.I))


def _tokens(value: str) -> set[str]:
    return {token for token in re.findall(r"[\wÀ-ÿ]+", value.casefold()) if len(token) >= 4}


_GENERIC_QUERY_TERMS = {
    "base", "diz", "sobre", "qual", "quais", "como", "pode", "podem",
    "falar", "explique", "mostra", "mostre", "informa", "informar",
}


def _supported_query(query: str, row: dict[str, Any], explicit: str | None) -> bool:
    terms = _tokens(query) - _GENERIC_QUERY_TERMS
    overlap = len(terms & _tokens(row["text"]))
    return bool(explicit and row["legal_locator"].rstrip(".") == explicit) or overlap >= 2


def verify_grounding(answer: dict[str, Any], evidence: list[dict[str, Any]]) -> dict[str, Any]:
    by_id = {str(row["id"]): row for row in evidence}
    citations = answer.get("citations", [])
    if answer.get("state") == "answered" and not citations:
        raise ValueError("answered_requires_citation")
    for citation in citations:
        row = by_id.get(str(citation.get("chunk_id")))
        if not row:
            raise ValueError("citation_not_in_evidence")
        if citation.get("locator") != row["legal_locator"] or citation.get("hash") != row["content_sha256"]:
            raise ValueError("citation_provenance_mismatch")
    return answer
