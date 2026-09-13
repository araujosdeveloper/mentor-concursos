"""Conector de busca na web (Tavily) usado como fallback de perguntas gerais."""

from __future__ import annotations

import hashlib
import json
import urllib.parse
from collections.abc import Callable
from datetime import UTC, datetime

from apps.external.cache import TransientCache
from apps.external.connectors import ExternalQuery, SourceEvidence

FetchFn = Callable[..., bytes]

_EDITAL_KEYWORDS = (
    "edital",
    "concurso",
    "banca",
    "vagas",
    "inscri",
    "certame",
    "seleção",
    "selecao",
    "prova",
    "cargo",
)
_PRIORITY_DOMAINS = ["grancursosonline.com.br", "estrategiaconcursos.com.br"]


def _is_edital_query(text: str) -> bool:
    lowered = text.casefold()
    return any(keyword in lowered for keyword in _EDITAL_KEYWORDS)


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

    def _search(
        self, query: ExternalQuery, *, text: str, include_domains: list[str] | None = None
    ) -> dict:
        url = f"{self._base_url}/search"
        domains_key = ",".join(include_domains or [])
        cache_key = f"tavily:{text.casefold()}:{query.max_results}:{domains_key}"
        content = self._cache.get(cache_key) if self._cache else None
        if content is None:
            payload: dict = {
                "query": text,
                "max_results": query.max_results,
                "search_depth": "basic",
            }
            if include_domains:
                payload["include_domains"] = include_domains
            raw = self._fetch(
                url,
                allowed_hosts={self._host()},
                headers={
                    "Authorization": f"Bearer {self._token}",
                    "Content-Type": "application/json",
                },
                method="POST",
                body=json.dumps(payload).encode(),
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

    def _recent_text(self, text: str) -> str:
        year = str(datetime.now(UTC).year)
        return text if year in text else f"{text} {year}"

    def query(self, query: ExternalQuery) -> list[SourceEvidence]:
        if not query.text.strip():
            return []
        results: list[SourceEvidence] = []
        seen: set[str] = set()
        if _is_edital_query(query.text):
            text = self._recent_text(query.text)
            for search_text, domains in (
                (text, _PRIORITY_DOMAINS),
                (text, None),
            ):
                payload = self._search(query, text=search_text, include_domains=domains)
                for item in self._results(payload):
                    evidence = self._to_evidence(item)
                    if evidence.url and evidence.url not in seen:
                        seen.add(evidence.url)
                        results.append(evidence)
                    if len(results) >= query.max_results:
                        return results
        else:
            for item in self._results(self._search(query, text=query.text)):
                results.append(self._to_evidence(item))
        return results[: query.max_results]
