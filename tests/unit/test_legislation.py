from __future__ import annotations

from apps.external.catalog import ConnectorSpec, SourceCatalog
from apps.external.connectors import ExternalQuery
from apps.external.connectors.legislation import LegislationConnector


class FakeCache:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    def get(self, key: str) -> str | None:
        return self.store.get(key)

    def set(self, key: str, value: str) -> None:
        self.store[key] = value


def _catalog() -> SourceCatalog:
    return SourceCatalog(
        segments={"administrativo": "Direito Administrativo"},
        connectors=(
            ConnectorSpec(
                key="lei-9784-camara",
                organization="Câmara dos Deputados",
                segment="administrativo",
                category="legislacao_federal",
                authority="primary_official",
                host="www2.camara.leg.br",
                canonical_url="https://www2.camara.leg.br/lei-9784",
                strategy="conditional_headers_then_sha256",
                max_redirects=3,
                enabled=True,
                note="Lei nº 9.784/1999",
            ),
        ),
    )


def _fetcher(content: bytes):
    def fetch(_url: str, allowed_hosts: set[str] | None = None) -> bytes:
        return content

    return fetch


def test_known_norm_returns_evidence_with_article() -> None:
    connector = LegislationConnector(
        _catalog(), None, _fetcher(b"<html>Art. 59. Texto do artigo.</html>")
    )
    evidence = connector.query(ExternalQuery(text="qual o prazo da Lei 9.784 art 59?"))
    assert len(evidence) == 1
    assert evidence[0].locator == "Art. 59"
    assert evidence[0].url == "https://www2.camara.leg.br/lei-9784"


def test_unknown_norm_returns_empty() -> None:
    connector = LegislationConnector(_catalog(), None, _fetcher(b"x"))
    assert connector.query(ExternalQuery(text="Lei 99999/2020 art 1")) == []


def test_missing_article_returns_empty() -> None:
    connector = LegislationConnector(_catalog(), None, _fetcher(b"<html>Art. 59. Texto.</html>"))
    assert connector.query(ExternalQuery(text="Lei 9.784 art 100")) == []


def test_cache_avoids_refetch() -> None:
    calls: list[str] = []

    def fetch(url: str, allowed_hosts: set[str] | None = None) -> bytes:
        calls.append(url)
        return b"<html>Art. 1. Texto.</html>"

    connector = LegislationConnector(_catalog(), FakeCache(), fetch)
    connector.query(ExternalQuery(text="Lei 9.784 art 1"))
    connector.query(ExternalQuery(text="Lei 9.784 art 1"))
    assert len(calls) == 1
