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

from apps.api.src.config import get_settings
from apps.api.src.dependencies import _postgres_check, _redis_check
from apps.worker.src.pipeline import claim_job, connect


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


def consume_once() -> int:
    """Consume um job com lease, sem executar conteúdo não confiável.

    O processamento especializado permanece explícito; jobs sem handler são
    encerrados com erro redigido, liberando o lease e permitindo observação.
    """
    worker_id = f"worker-{uuid.uuid4()}"
    job = claim_job(worker_id)
    if not job:
        return 0
    try:
        with connect() as connection, connection.transaction():
            connection.execute(
                "UPDATE mentor_concursos.ingestion_jobs SET status='failed', stage='failed', error_code='handler_unavailable', lease_owner=NULL, lease_expires_at=NULL WHERE id=%s AND lease_owner=%s",
                (job["id"], worker_id),
            )
            connection.execute(
                "INSERT INTO mentor_concursos.ingestion_events(job_id,stage,result,metadata) VALUES (%s,'failed','failed',%s)",
                (job["id"], '{"error_code":"handler_unavailable"}'),
            )
        logging.warning("ingestion_job_failed_handler_unavailable")
        return 1
    except Exception:
        logging.exception("ingestion_job_failure")
        return 1


if __name__ == "__main__":
    sys.exit(main())
