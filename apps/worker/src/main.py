import argparse
import json
import logging
import os
import signal
import sys
import threading
import urllib.error
import urllib.request

from apps.api.src.config import get_settings
from apps.api.src.dependencies import _postgres_check, _redis_check


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
    configure_logging()
    stopped = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stopped.set())
    signal.signal(signal.SIGINT, lambda *_: stopped.set())
    logging.info("worker_started")
    stopped.wait()
    logging.info("worker_stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
