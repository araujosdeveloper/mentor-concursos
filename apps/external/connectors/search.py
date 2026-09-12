"""Conector de busca na web (Tavily) usado como fallback de perguntas gerais."""

from __future__ import annotations

import hashlib
import json
import urllib.parse
from collections.abc import Callable

from apps.external.cache import TransientCache
from apps.external.connectors import ExternalQuery, SourceEvidence

FetchFn = Callable[..., bytes]


class SearchConnector:
    """Busca na web via Tavily; cada resultado é evidência citável (URL + trecho)."""

    def __init__(
        self, base_url: str, token: str, cache: TransientCache | None, fetch: FetchFn
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._cache = cache
        self._fetch = fetch

    def _host(self) -> str:
        return urllib.parse.urlparse(self._base_url).hostname or "api.tavily.com"

    def _search(self, query: ExternalQuery) -> dict:
        url = f"{self._base_url}/search"
        cache_key = f"tavily:{query.text.casefold()}:{query.max_results}"
        content = self._cache.get(cache_key) if self._cache else None
        if content is None:
            raw = self._fetch(
                url,
                allowed_hosts={self._host()},
                headers={
                    "Authorization": f"Bearer {self._token}",
                    "Content-Type": "application/json",
                },
                method="POST",
                body=json.dumps(
                    {
                        "query": query.text,
                        "max_results": query.max_results,
                        "search_depth": "basic",
                    }
                ).encode(),
            )
            content = raw.decode("utf-8", "replace")
            if self._cache:
                self._cache.set(cache_key, content)
        return json.loads(content)

    def _results(self, payload) -> list[dict]:
        if isinstance(payload, list):
            return payload
        if isinstance(payload.get("results"), list):
            return payload["results"]
        return []

    def _to_evidence(self, result: dict) -> SourceEvidence:
        title = result.get("title") or ""
        url = result.get("url") or ""
        snippet = result.get("content") or result.get("raw_content") or ""
        return SourceEvidence(
            source_name=title or url,
            locator=title or url,
            url=url,
            snippet=snippet[:1400],
            content_hash=hashlib.sha256(snippet.encode("utf-8")).hexdigest(),
            source_date=result.get("published_date"),
        )

    def query(self, query: ExternalQuery) -> list[SourceEvidence]:
        if not query.text.strip():
            return []
        payload = self._search(query)
        return [self._to_evidence(r) for r in self._results(payload)[: query.max_results]]
