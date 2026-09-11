# ruff: noqa: E501

import argparse
import json
import logging
import os
import signal
import sys
import threading
import urllib.error
import urllib.request
import uuid
from collections.abc import Callable
from typing import Any

from apps.api.src.config import get_settings
from apps.api.src.dependencies import _postgres_check, _redis_check
from apps.worker.src.pipeline import claim_job, connect

JobHandler = Callable[[dict[str, Any], str], None]
HANDLERS: dict[str, JobHandler] = {}
WORKER_ID = os.getenv("WORKER_ID") or f"worker-{uuid.uuid4()}"


def tika_check() -> bool:
    url = f"{os.environ.get('TIKA_URL', 'http://mentor-concursos-tika:9998').rstrip('/')}/version"
    try:
        with urllib.request.urlopen(url, timeout=3) as response:
            return response.status == 200 and bool(response.read(256).strip())
    except (OSError, urllib.error.URLError):
        return False


def dependencies_healthy() -> bool:
    settings = get_settings()
    return _postgres_check(settings) and _redis_check(settings) and tika_check()


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format='{"level":"%(levelname)s","message":"%(message)s"}',
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--healthcheck", action="store_true")
    parser.add_argument("--once", action="store_true", help="consome no máximo um job")
    args = parser.parse_args()
    if args.healthcheck:
        healthy = dependencies_healthy()
        print(
            json.dumps(
                {
                    "status": "ok" if healthy else "error",
                    "service": "mentor-concursos-worker",
                }
            )
        )
        return 0 if healthy else 1
    if args.once:
        return consume_once()
    configure_logging()
    stopped = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stopped.set())
    signal.signal(signal.SIGINT, lambda *_: stopped.set())
    logging.info("worker_started")
    consume_enabled = os.getenv("WORKER_CONSUME_ENABLED", "false").lower() == "true"
    while not stopped.wait(float(os.getenv("WORKER_POLL_SECONDS", "5"))):
        if consume_enabled:
            consume_once()
    logging.info("worker_stopped")
    return 0


def consume_once(handlers: dict[str, JobHandler] | None = None) -> int:
    """Consome um job somente quando um handler explícito foi fornecido.

    A ausência de handler é fail-closed e não reclama nem altera jobs. Testes
    podem injetar um handler de fixture sintética sem habilitar consumo real.
    """
    active_handlers = HANDLERS if handlers is None else handlers
    if not active_handlers:
        logging.info("worker_no_handlers_enabled")
        return 0
    job = claim_job(WORKER_ID, tuple(sorted(active_handlers)))
    if not job:
        return 0
    handler = active_handlers.get(str(job["source_type"]))
    if handler is None:
        logging.error("worker_claimed_unsupported_job")
        return 1
    try:
        handler(job, WORKER_ID)
        return 0
    except Exception:
        logging.error("ingestion_job_failure")
        with connect() as connection, connection.transaction():
            exhausted = int(job["attempts"]) >= 5
            connection.execute(
                """UPDATE mentor_concursos.ingestion_jobs
                   SET status=%s,stage=%s,error_code='handler_failed',lease_owner=NULL,
                       lease_expires_at=NULL,next_attempt_at=CASE WHEN %s THEN NULL ELSE CURRENT_TIMESTAMP + interval '1 minute' END
                   WHERE id=%s AND lease_owner=%s""",
                ("failed" if exhausted else "queued", "failed" if exhausted else "queued", exhausted, job["id"], WORKER_ID),
            )
            connection.execute(
                "INSERT INTO mentor_concursos.ingestion_events(job_id,stage,result,metadata) VALUES (%s,'handler','failed',%s)",
                (job["id"], json.dumps({"error_code": "handler_failed", "retry_exhausted": exhausted})),
            )
        return 1


if __name__ == "__main__":
    sys.exit(main())
