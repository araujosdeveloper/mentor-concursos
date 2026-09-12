from __future__ import annotations

import json

from apps.external.connectors import ExternalQuery
from apps.external.connectors.search import SearchConnector


def _connector(fetch) -> SearchConnector:
    return SearchConnector("https://api.tavily.com", "token", None, fetch)


def _fetch_with(payload: dict):
    calls: dict[str, str] = {}

    def fetch(url: str, allowed_hosts=None, headers=None, method="GET", body=None) -> bytes:
        calls["url"] = url
        calls["method"] = method
        calls["auth"] = (headers or {}).get("Authorization", "")
        calls["body"] = (body or b"").decode("utf-8", "replace")
        return json.dumps(payload).encode()

    fetch.calls = calls  # type: ignore[attr-defined]
    return fetch


def test_search_returns_evidence_with_citation() -> None:
    fetch = _fetch_with(
        {
            "results": [
                {
                    "title": "Concurso INSS 2025",
                    "url": "https://example.com/inss",
                    "content": "O edital do INSS prevê 1000 vagas para Técnico do Seguro Social.",
                }
            ]
        }
    )
    evidence = _connector(fetch).query(ExternalQuery(text="qual o último edital do INSS?"))
    assert fetch.calls["method"] == "POST"
    assert fetch.calls["auth"] == "Bearer token"
    assert len(evidence) == 1
    assert evidence[0].url == "https://example.com/inss"
    assert "1000 vagas" in evidence[0].snippet


def test_search_tolerates_missing_results() -> None:
    fetch = _fetch_with({"detail": "erro"})
    assert _connector(fetch).query(ExternalQuery(text="qualquer coisa")) == []


def test_search_ignores_blank_query() -> None:
    fetch = _fetch_with({"results": []})
    assert _connector(fetch).query(ExternalQuery(text="   ")) == []
