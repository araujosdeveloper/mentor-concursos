"""Conector de legislação: localiza uma norma oficial e extrai o artigo citado."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable

from apps.external.cache import TransientCache
from apps.external.catalog import SourceCatalog
from apps.external.connectors import ExternalQuery, SourceEvidence

_NORM = re.compile(r"lei\s+(?:n[ºo]\.?\s*)?(\d+(?:\.\d+)*(?:/\d+)?)", re.I)
_ARTICLE = re.compile(r"\bart(?:igo)?\.?\s*(\d+[ºo]?(?:\s*-\s*[A-Za-z])?)", re.I)
FetchFn = Callable[..., bytes]


def _strip_html(html: str) -> str:
    return re.sub(r"<[^>]+>", " ", html)


def _normalize_norm(value: str) -> str:
    return re.sub(r"[^0-9]", "", value)


def _extract_snippet(text: str, article: str | None, limit: int = 1400) -> str | None:
    if not article:
        return re.sub(r"\s+", " ", text).strip()[:limit]
    pattern = re.compile(rf"\bArt\.?\s*{re.escape(article)}(?![0-9])", re.I)
    match = pattern.search(text)
    if not match:
        return None
    return re.sub(r"\s+", " ", text[match.start() : match.start() + limit])


class LegislationConnector:
    """Consulta normas oficiais já mapeadas no catálogo (com URL canônica)."""

    def __init__(
        self, catalog: SourceCatalog, cache: TransientCache | None, fetch: FetchFn
    ) -> None:
        self._catalog = catalog
        self._cache = cache
        self._fetch = fetch

    def _find_source(self, norm_digits: str):
        for source in self._catalog.connectors:
            if source.category != "legislacao_federal" or not source.enabled:
                continue
            haystack = f"{source.key} {source.note or ''}".lower()
            if norm_digits and norm_digits in _normalize_norm(haystack):
                return source
        return None

    def query(self, query: ExternalQuery) -> list[SourceEvidence]:
        norm = _NORM.search(query.text)
        if not norm:
            return []
        source = self._find_source(_normalize_norm(norm.group(1)))
        if source is None or not source.canonical_url:
            return []
        article = _ARTICLE.search(query.text)
        article_ref = article.group(1) if article else None
        url = source.canonical_url

        content = self._cache.get(url) if self._cache else None
        if content is None:
            raw = self._fetch(url, allowed_hosts={source.host})
            content = raw.decode("utf-8", "replace")
            if self._cache:
                self._cache.set(url, content)
        text = _strip_html(content)
        snippet = _extract_snippet(text, article_ref)
        if snippet is None:
            return []
        return [
            SourceEvidence(
                source_name=source.organization,
                locator=f"Art. {article_ref}" if article_ref else "texto",
                url=url,
                snippet=snippet,
                content_hash=hashlib.sha256(content.encode("utf-8")).hexdigest(),
            )
        ]
