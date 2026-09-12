from __future__ import annotations

import json

from apps.external.connectors import ExternalQuery
from apps.external.connectors.jurisprudence import JurisprudenceConnector

BASE = "https://jurisprudencias.ai/api/v1"


def _connector(fetch) -> JurisprudenceConnector:
    return JurisprudenceConnector(BASE, "token", None, fetch)


def _decisions_fetch(decisions: list[dict]):
    calls: dict[str, str] = {}

    def fetch(url: str, allowed_hosts=None, headers=None) -> bytes:
        calls["url"] = url
        calls["auth"] = headers.get("Authorization", "") if headers else ""
        return json.dumps({"decisions": decisions}).encode()

    fetch.calls = calls  # type: ignore[attr-defined]
    return fetch


def test_stj_court_detection_and_evidence_mapping() -> None:
    fetch = _decisions_fetch(
        [
            {
                "court": "stj",
                "process_number": "REsp 1.234.567",
                "excerpt": "trecho da ementa",
                "url": "https://processo.stj.jus.br/x",
                "publication_date": "2024-01-01",
            }
        ]
    )
    evidence = _connector(fetch).query(ExternalQuery(text="o que diz o STJ sobre dano moral?"))
    assert len(evidence) == 1
    assert "courts/stj/decisions" in fetch.calls["url"]
    assert fetch.calls["auth"] == "Bearer token"
    assert evidence[0].locator == "REsp 1.234.567"
    assert evidence[0].url == "https://processo.stj.jus.br/x"


def test_full_name_alias_resolves_court() -> None:
    fetch = _decisions_fetch([{"court": "stf", "excerpt": "x", "url": "u"}])
    _connector(fetch).query(ExternalQuery(text="entendimento do supremo tribunal federal sobre X"))
    assert "courts/stf/decisions" in fetch.calls["url"]


def test_jurisprudence_keyword_uses_default_courts() -> None:
    fetch = _decisions_fetch([{"court": "stf", "excerpt": "x", "url": "u"}])
    evidence = _connector(fetch).query(ExternalQuery(text="jurisprudência sobre dano moral"))
    assert evidence


def test_legislation_query_does_not_trigger_jurisprudence() -> None:
    called = []

    def fetch(url: str, allowed_hosts=None, headers=None) -> bytes:
        called.append(url)
        return b"{}"

    evidence = _connector(fetch).query(ExternalQuery(text="Lei 9.784 art 59"))
    assert evidence == []
    assert called == []


def test_tolerant_response_parsing() -> None:
    fetch = _decisions_fetch([{"process_number": "123", "full_text": "texto integral", "link": "https://x"}])
    evidence = _connector(fetch).query(ExternalQuery(text="decisão do STJ sobre X"))
    assert evidence[0].locator == "123"
    assert evidence[0].url == "https://x"
    assert "texto integral" in evidence[0].snippet
