from __future__ import annotations

import pytest

from apps.external import service as external_service
from apps.external.connectors import ExternalQuery, SourceEvidence


class FixtureConnector:
    def __init__(self, locator: str) -> None:
        self._locator = locator

    def query(self, query: ExternalQuery) -> list[SourceEvidence]:
        return [
            SourceEvidence(
                source_name="Fixture",
                locator=self._locator,
                url="https://example.com/1",
                snippet="texto sintético",
                content_hash="a" * 64,
            )
        ]


def _register(monkeypatch, categories: tuple[str, ...] = ("legislacao_federal",)) -> None:
    monkeypatch.setattr(external_service, "CONNECTORS", {})
    for category in categories:
        external_service.CONNECTORS[category] = FixtureConnector("Art. 1º")


def test_query_with_category_uses_connector(monkeypatch) -> None:
    _register(monkeypatch)
    evidence = external_service._run_query(
        {"query": "qual o prazo?", "category": "legislacao_federal"}
    )
    assert len(evidence) == 1
    assert evidence[0].locator == "Art. 1º"


def test_query_missing_is_rejected(monkeypatch) -> None:
    _register(monkeypatch)
    with pytest.raises(ValueError, match="query_missing"):
        external_service._run_query({"query": "   "})


def test_unavailable_category_is_rejected(monkeypatch) -> None:
    _register(monkeypatch)
    with pytest.raises(ValueError, match="category_unavailable"):
        external_service._run_query({"query": "x", "category": "jurisprudencia"})


def test_query_without_category_merges_all_connectors(monkeypatch) -> None:
    _register(monkeypatch, ("legislacao_federal", "jurisprudencia"))
    evidence = external_service._run_query({"query": "x"})
    assert len(evidence) == 2


def test_max_results_caps_evidence(monkeypatch) -> None:
    _register(monkeypatch, ("legislacao_federal", "jurisprudencia"))
    evidence = external_service._run_query({"query": "x", "max_results": 1})
    assert len(evidence) == 1
