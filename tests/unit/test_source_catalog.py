from __future__ import annotations

from pathlib import Path

import pytest

from apps.external.catalog import load_catalog

REPO = Path(__file__).parents[2]
REAL_CATALOG = REPO / "config" / "official-sources.yaml"


def test_real_catalog_loads_and_validates() -> None:
    catalog = load_catalog(REAL_CATALOG)
    assert "administrativo" in catalog.segments
    assert "constitucional" in catalog.segments
    keys = {c.key for c in catalog.connectors}
    assert "lei-9784-camara" in keys
    assert "jurisprudencias-ai" in keys
    enabled = catalog.enabled()
    assert "lei-9784-camara" in [c.key for c in enabled]
    assert "constituicao-federal-planalto" in [c.key for c in enabled]
    assert "jurisprudencias-ai" in [c.key for c in enabled]
    assert len(enabled) == 11


def test_enabled_filters_by_category_and_segment() -> None:
    catalog = load_catalog(REAL_CATALOG)
    assert catalog.enabled(category="jurisprudencia")[0].key == "jurisprudencias-ai"
    assert catalog.enabled(category="legislacao_federal")[0].key == "lei-9784-camara"
    assert catalog.enabled(category="constituicao")[0].key == "constituicao-federal-planalto"


def _catalog(tmp_path: Path, sources: dict) -> None:
    content = {
        "version": 1,
        "segments": {"administrativo": "Direito Administrativo"},
        "sources": sources,
    }
    import yaml

    (tmp_path / "catalog.yaml").write_text(yaml.safe_dump(content), encoding="utf-8")


def test_invalid_category_rejected(tmp_path: Path) -> None:
    _catalog(
        tmp_path,
        {
            "x": {
                "organization": "org",
                "segment": "administrativo",
                "category": "desconhecida",
                "host": "example.com",
            }
        },
    )
    with pytest.raises(ValueError, match="source_invalid_category"):
        load_catalog(tmp_path / "catalog.yaml")


def test_invalid_host_rejected(tmp_path: Path) -> None:
    _catalog(
        tmp_path,
        {
            "x": {
                "organization": "org",
                "segment": "administrativo",
                "category": "legislacao_federal",
                "host": "https://example.com",
            }
        },
    )
    with pytest.raises(ValueError, match="source_invalid_host"):
        load_catalog(tmp_path / "catalog.yaml")


def test_unknown_segment_rejected(tmp_path: Path) -> None:
    _catalog(
        tmp_path,
        {
            "x": {
                "organization": "org",
                "segment": "inexistente",
                "category": "legislacao_federal",
                "host": "example.com",
            }
        },
    )
    with pytest.raises(ValueError, match="source_unknown_segment"):
        load_catalog(tmp_path / "catalog.yaml")


def test_unsupported_version_rejected(tmp_path: Path) -> None:
    import yaml

    (tmp_path / "catalog.yaml").write_text(
        yaml.safe_dump({"version": 2, "segments": {}, "sources": {}}), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="catalog_version_unsupported"):
        load_catalog(tmp_path / "catalog.yaml")
