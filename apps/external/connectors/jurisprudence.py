"""Conector de jurisprudência via agregador (jurisprudencias.ai).

A busca é feita no agregador, mas cada resultado cita a URL do documento
original no portal do tribunal, preservando a rastreabilidade (ADR-020).
"""

from __future__ import annotations

import hashlib
import json
import re
import urllib.parse
from collections.abc import Callable

from apps.external.cache import TransientCache
from apps.external.connectors import ExternalQuery, SourceEvidence

FetchFn = Callable[..., bytes]

_NAME_ALIASES = {
    "supremo tribunal federal": "stf",
    "superior tribunal de justiça": "stj",
    "tribunal superior do trabalho": "tst",
}
_COURT_PATTERN = re.compile(r"\b(stf|stj|tst|trf[1-5]|tj[a-z]{2}|carf)\b", re.I)
_JURIS_KEYWORDS = (
    "jurisprudência",
    "jurisprudencia",
    "decisão",
    "decisao",
    "súmula",
    "sumula",
    "acórdão",
    "acordao",
    "precedente",
    "entendimento",
    "tese",
    "julgado",
    "recurso especial",
    "recurso extraordinário",
    "recurso extraordinario",
)
_DEFAULT_COURTS = ("stf", "stj")

_URL_KEYS = ("url", "source_url", "document_url", "link", "original_url")
_PROCESS_KEYS = ("process_number", "numero_processo", "numero_processo_cnj")


class JurisprudenceConnector:
    """Consulta decisões reais via agregador e cita a fonte original."""

    def __init__(
        self, base_url: str, token: str, cache: TransientCache | None, fetch: FetchFn
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._cache = cache
        self._fetch = fetch

    def _host(self) -> str:
        return urllib.parse.urlparse(self._base_url).hostname or "jurisprudencias.ai"

    def _resolve_courts(self, text: str) -> list[str]:
        lowered = text.casefold()
        for name, code in sorted(_NAME_ALIASES.items(), key=lambda kv: -len(kv[0])):
            if name in lowered:
                return [code]
        match = _COURT_PATTERN.search(lowered)
        if match:
            return [match.group(1)]
        if any(keyword in lowered for keyword in _JURIS_KEYWORDS):
            return list(_DEFAULT_COURTS)
        return []

    def _search(self, court: str, q: str) -> dict:
        url = f"{self._base_url}/courts/{court}/decisions?q={urllib.parse.quote(q)}&page=0"
        content = self._cache.get(url) if self._cache else None
        if content is None:
            raw = self._fetch(
                url,
                allowed_hosts={self._host()},
                headers={"Authorization": f"Bearer {self._token}"},
            )
            content = raw.decode("utf-8", "replace")
            if self._cache:
                self._cache.set(url, content)
        return json.loads(content)

    def _decisions(self, payload) -> list[dict]:
        if isinstance(payload, list):
            return payload
        for key in ("decisions", "results", "data", "items"):
            if isinstance(payload.get(key), list):
                return payload[key]
        return []

    def _to_evidence(self, decision: dict) -> SourceEvidence:
        excerpt = decision.get("excerpt") or decision.get("full_text") or ""
        url = next((decision.get(k) for k in _URL_KEYS if decision.get(k)), "")
        process = next((str(decision.get(k)) for k in _PROCESS_KEYS if decision.get(k)), "")
        return SourceEvidence(
            source_name=str(decision.get("court") or decision.get("tribunal") or "jurisprudência"),
            locator=process,
            url=url,
            snippet=excerpt[:1400],
            content_hash=hashlib.sha256(excerpt.encode("utf-8")).hexdigest(),
            source_date=decision.get("publication_date") or decision.get("data_publicacao"),
        )

    def query(self, query: ExternalQuery) -> list[SourceEvidence]:
        courts = self._resolve_courts(query.text)
        evidence: list[SourceEvidence] = []
        for court in courts:
            payload = self._search(court, query.text)
            for decision in self._decisions(payload):
                evidence.append(self._to_evidence(decision))
                if len(evidence) >= query.max_results:
                    return evidence
        return evidence
