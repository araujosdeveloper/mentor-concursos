"""Serviço interno offline de embeddings com contrato E5 estável."""

# ruff: noqa: E501

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .knowledge import EMBEDDING_DIMENSIONS, MODEL_ID, MODEL_REVISION, hash_embedding


class Handler(BaseHTTPRequestHandler):
    server_version = "mentor-embeddings/0.1"

    def do_GET(self) -> None:  # noqa: N802
        if self.path != "/health":
            self.send_error(404)
            return
        self._json(200, {"status": "ok", "model_id": MODEL_ID, "revision": MODEL_REVISION, "dimensions": EMBEDDING_DIMENSIONS})

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/embed":
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("content-length", "0"))
            if length <= 0 or length > 256 * 1024:
                raise ValueError("payload_too_large")
            body = json.loads(self.rfile.read(length))
            texts = body.get("texts")
            if not isinstance(texts, list) or not 1 <= len(texts) <= 16 or any(not isinstance(t, str) or len(t) > 12000 for t in texts):
                raise ValueError("invalid_batch")
            vectors = [hash_embedding(text, body.get("prefix", "passage:")) for text in texts]
            self._json(200, {"model_id": MODEL_ID, "revision": MODEL_REVISION, "dimensions": EMBEDDING_DIMENSIONS, "vectors": vectors})
        except (ValueError, json.JSONDecodeError):
            self._json(422, {"detail": "embedding_request_invalid"})

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
    ThreadingHTTPServer(("0.0.0.0", 8090), Handler).serve_forever()


if __name__ == "__main__":
    main()
