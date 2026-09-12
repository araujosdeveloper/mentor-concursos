"""Conector de legislação: localiza uma norma oficial e extrai o artigo citado."""

from __future__ import annotations

import hashlib
import html
import re
from collections.abc import Callable

from apps.external.cache import TransientCache
from apps.external.catalog import SourceCatalog
from apps.external.connectors import ExternalQuery, SourceEvidence

FetchFn = Callable[..., bytes]

_NORM = re.compile(
    r"(?:lei|decreto-lei)\s+(?:n[ºo]\.?\s*)?(\d+(?:\.\d+)*(?:/\d+)?)", re.I
)
_ARTICLE = re.compile(r"\bart(?:igo)?\.?\s*(\d+[ºo]?(?:\s*-\s*[A-Za-z])?)", re.I)
_CONSTITUTION = re.compile(r"\bconstitui|\bcf\b|\bcarta magna\b", re.I)

_CODE_ALIASES = {
    "consolidação das leis": "clt-decreto-lei-5452",
    "código de processo civil": "cpc-lei-13105",
    "código de processo penal": "cpp-decreto-lei-3689",
    "código de defesa do consumidor": "cdc-lei-8078",
    "código do consumidor": "cdc-lei-8078",
    "código eleitoral": "codigo-eleitoral-4737",
    "código tributário": "ctn-lei-5172",
    "código civil": "codigo-civil-lei-10406",
    "código penal": "codigo-penal-decreto-lei-2848",
    "lei de responsabilidade fiscal": "lc-101-lrf",
    "lei de acesso à informação": "lei-12527-lai",
    "lei de acesso a informação": "lei-12527-lai",
    "lei de improbidade": "lei-8429-improbidade",
    "mandado de segurança": "lei-12016-ms",
    "abuso de autoridade": "lei-13869-abuso",
    "crimes ambientais": "lei-9605-ambiental",
    "política nacional do meio ambiente": "lei-6938-ambiental",
    "sociedades anônimas": "lei-6404-sa",
    "sociedades por ações": "lei-6404-sa",
    "lrf": "lc-101-lrf",
    "lai": "lei-12527-lai",
    "clt": "clt-decreto-lei-5452",
    "ctn": "ctn-lei-5172",
    "cpc": "cpc-lei-13105",
    "cpp": "cpp-decreto-lei-3689",
    "cdc": "cdc-lei-8078",
}


def _strip_html(html_str: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", " ", html_str))


def _decode(raw: bytes) -> str:
    """Decodifica o HTML preferindo UTF-8 e caindo para o charset declarado ou cp1252."""
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        head = raw[:2048].decode("latin-1", "replace")
        match = re.search(r'charset=["\']?([\w-]+)', head, re.I)
        if match:
            try:
                return raw.decode(match.group(1))
            except (UnicodeDecodeError, LookupError):
                pass
        return raw.decode("cp1252")


def _normalize_norm(value: str) -> str:
    return re.sub(r"[^0-9]", "", value)


def _extract_snippet(text: str, article: str | None, limit: int = 2400) -> str | None:
    if not article:
        return re.sub(r"\s+", " ", text).strip()[:limit]
    pattern = re.compile(rf"\bArt\.\s*{re.escape(article)}(?![0-9])")
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

    def _enabled_sources(self, category: str):
        return [
            s for s in self._catalog.connectors if s.category == category and s.enabled
        ]

    def _source_by_key(self, key: str):
        for source in self._catalog.connectors:
            if source.key == key and source.enabled:
                return source
        return None

    def _find_by_norm(self, norm_digits: str):
        for source in self._enabled_sources("legislacao_federal"):
            haystack = f"{source.key} {source.note or ''}".lower()
            if norm_digits and norm_digits in _normalize_norm(haystack):
                return source
        return None

    def _resolve_source(self, text: str):
        if _CONSTITUTION.search(text):
            for source in self._enabled_sources("constituicao"):
                return source
        norm = _NORM.search(text)
        if norm:
            return self._find_by_norm(_normalize_norm(norm.group(1)))
        lowered = text.casefold()
        for alias, key in _CODE_ALIASES.items():
            if alias in lowered:
                return self._source_by_key(key)
        return None

    def query(self, query: ExternalQuery) -> list[SourceEvidence]:
        source = self._resolve_source(query.text)
        if source is None or not source.canonical_url:
            return []
        article = _ARTICLE.search(query.text)
        article_ref = article.group(1) if article else None
        url = source.canonical_url

        content = self._cache.get(url) if self._cache else None
        if content is None:
            raw = self._fetch(url, allowed_hosts={source.host})
            content = _decode(raw)
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
