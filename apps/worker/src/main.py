import argparse
import json
import logging
import signal
import sys
import threading


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
        print(json.dumps({"status": "ok", "service": "mentor-concursos-worker"}))
        return 0
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
