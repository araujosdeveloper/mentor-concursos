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


def _source(key: str, category: str, note: str, url: str, enabled: bool = True) -> ConnectorSpec:
    return ConnectorSpec(
        key=key,
        organization="Órgão oficial",
        segment="administrativo",
        category=category,
        authority="primary_official",
        host="example.com",
        canonical_url=url,
        strategy="conditional_headers_then_sha256",
        max_redirects=3,
        enabled=enabled,
        note=note,
    )


def _catalog() -> SourceCatalog:
    return SourceCatalog(
        segments={
            "administrativo": "Direito Administrativo",
            "constitucional": "Direito Constitucional",
        },
        connectors=(
            _source("lei-9784-camara", "legislacao_federal", "Lei nº 9.784/1999", "https://e.com/9784"),
            _source("constituicao-federal", "constituicao", "Constituição de 1988", "https://e.com/cf"),
            _source(
                "clt-decreto-lei-5452",
                "legislacao_federal",
                "CLT — Decreto-Lei nº 5.452/1943",
                "https://e.com/clt",
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
    assert evidence[0].url == "https://e.com/9784"


def test_unknown_norm_returns_empty() -> None:
    connector = LegislationConnector(_catalog(), None, _fetcher(b"x"))
    assert connector.query(ExternalQuery(text="Lei 99999/2020 art 1")) == []


def test_missing_article_returns_empty() -> None:
    connector = LegislationConnector(_catalog(), None, _fetcher(b"<html>Art. 59. Texto.</html>"))
    assert connector.query(ExternalQuery(text="Lei 9.784 art 100")) == []


def test_constitution_keyword_resolves_source() -> None:
    connector = LegislationConnector(
        _catalog(), None, _fetcher(b"<html>Art. 5. Todos sao iguais.</html>")
    )
    evidence = connector.query(ExternalQuery(text="Constituicao art 5"))
    assert len(evidence) == 1
    assert evidence[0].url == "https://e.com/cf"


def test_code_alias_resolves_source() -> None:
    connector = LegislationConnector(
        _catalog(), None, _fetcher(b"<html>Art. 3. Considera-se empregado.</html>")
    )
    evidence = connector.query(ExternalQuery(text="CLT art 3"))
    assert len(evidence) == 1
    assert evidence[0].url == "https://e.com/clt"


def test_decode_falls_back_to_cp1252() -> None:
    from apps.external.connectors.legislation import _decode

    assert "º" in _decode("Art. 3º - Considera-se empregado".encode("cp1252"))


def test_lowercase_cross_reference_is_not_matched() -> None:
    connector = LegislationConnector(
        _catalog(),
        None,
        _fetcher(b"<html>art. 59 desta Lei ... Art. 59. Texto oficial do artigo.</html>"),
    )
    evidence = connector.query(ExternalQuery(text="Lei 9.784 art 59"))
    assert len(evidence) == 1
    assert "Texto oficial" in evidence[0].snippet


def test_cache_avoids_refetch() -> None:
    calls: list[str] = []

    def fetch(url: str, allowed_hosts: set[str] | None = None) -> bytes:
        calls.append(url)
        return b"<html>Art. 1. Texto.</html>"

    connector = LegislationConnector(_catalog(), FakeCache(), fetch)
    connector.query(ExternalQuery(text="Lei 9.784 art 1"))
    connector.query(ExternalQuery(text="Lei 9.784 art 1"))
    assert len(calls) == 1
