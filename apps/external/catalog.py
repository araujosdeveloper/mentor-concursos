"""Carregador determinístico do catálogo de fontes oficiais (ADR-020)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

CATEGORIES = frozenset(
    {
        "constituicao",
        "legislacao_federal",
        "sumula",
        "jurisprudencia",
    }
)
STRATEGIES = frozenset(
    {
        "conditional_headers_then_sha256",
        "search_endpoint",
    }
)
DEFAULT_MAX_REDIRECTS = 3


@dataclass(frozen=True)
class ConnectorSpec:
    """Especificação imutável de um conector oficial."""

    key: str
    organization: str
    segment: str | None
    category: str
    authority: str
    host: str
    canonical_url: str | None
    strategy: str
    max_redirects: int
    enabled: bool


@dataclass(frozen=True)
class SourceCatalog:
    """Catálogo validado de conectores oficiais."""

    segments: dict[str, str]
    connectors: tuple[ConnectorSpec, ...]

    def enabled(
        self, *, category: str | None = None, segment: str | None = None
    ) -> list[ConnectorSpec]:
        result = [c for c in self.connectors if c.enabled]
        if category is not None:
            result = [c for c in result if c.category == category]
        if segment is not None:
            result = [c for c in result if c.segment == segment]
        return result


def _host_is_valid(value: str) -> bool:
    return bool(value) and "://" not in value and "/" not in value and " " not in value


def load_catalog(path: Path) -> SourceCatalog:
    """Lê e valida o catálogo, falhando de forma determinística em dados inválidos."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if raw.get("version") != 1:
        raise ValueError("catalog_version_unsupported")
    segments = raw.get("segments") or {}
    if not isinstance(segments, dict) or not segments:
        raise ValueError("catalog_segments_missing")
    sources = raw.get("sources") or {}
    if not isinstance(sources, dict):
        raise ValueError("catalog_sources_missing")

    connectors: list[ConnectorSpec] = []
    for key, entry in sources.items():
        if not isinstance(entry, dict):
            raise ValueError(f"source_not_mapping:{key}")
        category = entry.get("category")
        if category not in CATEGORIES:
            raise ValueError(f"source_invalid_category:{key}")
        strategy = entry.get("strategy", "conditional_headers_then_sha256")
        if strategy not in STRATEGIES:
            raise ValueError(f"source_invalid_strategy:{key}")
        host = entry.get("host", "")
        if not _host_is_valid(host):
            raise ValueError(f"source_invalid_host:{key}")
        segment = entry.get("segment")
        if segment is not None and segment not in segments:
            raise ValueError(f"source_unknown_segment:{key}:{segment}")
        connectors.append(
            ConnectorSpec(
                key=str(key),
                organization=str(entry.get("organization", "")),
                segment=segment,
                category=category,
                authority=str(entry.get("authority", "primary_official")),
                host=host,
                canonical_url=entry.get("canonical_url"),
                strategy=strategy,
                max_redirects=int(entry.get("max_redirects", DEFAULT_MAX_REDIRECTS)),
                enabled=bool(entry.get("enabled", False)),
            )
        )

    keys = {c.key for c in connectors}
    if len(keys) != len(connectors):
        raise ValueError("catalog_duplicate_keys")
    return SourceCatalog(segments=dict(segments), connectors=tuple(connectors))
