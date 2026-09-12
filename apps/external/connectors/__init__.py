"""Conectores de consulta externa e contratos compartilhados."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ExternalQuery:
    """Consulta direcionada a um conector oficial, sem ingestão."""

    text: str
    category: str | None = None
    segment: str | None = None
    max_results: int = 5


@dataclass(frozen=True)
class SourceEvidence:
    """Evidência externa citável, extraída de fonte oficial no momento da consulta."""

    source_name: str
    locator: str
    url: str
    snippet: str
    content_hash: str
    source_date: str | None = None


class Connector(Protocol):
    """Interface de um conector de consulta a uma fonte oficial."""

    def query(self, query: ExternalQuery) -> list[SourceEvidence]: ...
