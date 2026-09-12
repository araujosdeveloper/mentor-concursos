"""Serviço de consulta externa ao vivo a fontes oficiais (ADR-020).

Nenhum conteúdo é ingerido ou indexado; cada consulta recupera evidências de
sites oficiais, com cache transitório apenas para performance.
"""

# ruff: noqa: E501

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from apps.external.cache import TransientCache
from apps.external.catalog import SourceCatalog, load_catalog
from apps.external.connectors import Connector, ExternalQuery, SourceEvidence
from apps.external.connectors.jurisprudence import JurisprudenceConnector
from apps.external.connectors.legislation import LegislationConnector
from apps.external.fetch import fetch

CATALOG_PATH = Path(os.getenv("CATALOG_PATH", "/app/config/official-sources.yaml"))
PORT = int(os.getenv("EXTERNAL_PORT", "8091"))
logger = logging.getLogger("mentor.external")

catalog: SourceCatalog | None = None
cache: TransientCache | None = None
CONNECTORS: dict[str, Connector] = {}


def register(category: str, connector: Connector) -> None:
    """Registra um conector real por categoria; chamado no bootstrap da produção."""
    CONNECTORS[category] = connector


def populate_connectors() -> None:
    """Registra os conectores disponíveis na produção (Fase 2)."""
    if catalog is None or cache is None:
        raise RuntimeError("catalog_not_loaded")
    register("legislacao_federal", LegislationConnector(catalog, cache, fetch))
    token = _read_jurisprudencia_token()
    if token:
        base = os.getenv("JURISPRUDENCIAS_BASE_URL", "https://jurisprudencias.ai/api/v1")
        register("jurisprudencia", JurisprudenceConnector(base, token, cache, fetch))
    else:
        logger.info("jurisprudence_token_missing")


def _read_jurisprudencia_token() -> str:
    path = os.getenv("JURISPRUDENCIAS_API_TOKEN_FILE", "/run/secrets/jurisprudencias_api_token")
    try:
        return Path(path).read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _run_query(body: dict[str, object]) -> list[SourceEvidence]:
    text = str(body.get("query", "")).strip()
    if not text:
        raise ValueError("query_missing")
    category = body.get("category")
    if category is not None and not isinstance(category, str):
        raise ValueError("category_invalid")
    query = ExternalQuery(
        text=text,
        category=category,
        segment=body.get("segment") if isinstance(body.get("segment"), str) else None,
        max_results=int(body.get("max_results", 5)),
    )
    if category:
        connector = CONNECTORS.get(category)
        if connector is None:
            raise ValueError("category_unavailable")
        selected = [connector]
    else:
        selected = list(CONNECTORS.values())
    evidence: list[SourceEvidence] = []
    for connector in selected:
        evidence.extend(connector.query(query))
    return evidence[: query.max_results]


class Handler(BaseHTTPRequestHandler):
    server_version = "mentor-external/0.1"

    def do_GET(self) -> None:  # noqa: N802
        if self.path != "/health":
            self.send_error(404)
            return
        self._json(
            200,
            {
                "status": "ok",
                "connectors": sorted(CONNECTORS),
                "catalog_sources": len(catalog.connectors) if catalog else 0,
            },
        )

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/query":
            self.send_error(404)
            return
        started = time.perf_counter()
        try:
            length = int(self.headers.get("content-length", "0"))
            if length <= 0 or length > 64 * 1024:
                raise ValueError("payload_too_large")
            body = json.loads(self.rfile.read(length))
            evidence = _run_query(body)
            self._json(
                200,
                {
                    "evidence": [asdict(item) for item in evidence],
                    "duration_ms": int((time.perf_counter() - started) * 1000),
                },
            )
        except (ValueError, json.JSONDecodeError) as exc:
            self._json(422, {"detail": str(exc)})
        except Exception:
            logger.exception("external_query_failed")
            self._json(503, {"detail": "external_unavailable"})

    def _json(self, code: int, payload: dict[str, object]) -> None:
        encoded = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, _format: str, *_args: object) -> None:
        return


def main() -> None:
    global catalog, cache
    logging.basicConfig(level=logging.INFO, format='{"level":"%(levelname)s","message":"%(message)s"}')
    catalog = load_catalog(CATALOG_PATH)
    cache = TransientCache(
        host=os.getenv("REDIS_HOST", "mentor-concursos-redis"),
        port=int(os.getenv("REDIS_PORT", "6379")),
        password=os.getenv("REDIS_PASSWORD", ""),
        ttl_seconds=int(os.getenv("EXTERNAL_CACHE_TTL_SECONDS", "300")),
    )
    populate_connectors()
    logger.info("external_service_started sources=%s connectors=%s", len(catalog.connectors), sorted(CONNECTORS))
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
