"""Offline E5 embedding service; production fails closed without real weights."""

# ruff: noqa: E501

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

MODEL_ID = "intfloat/multilingual-e5-small"
MODEL_REVISION = "fd1525a9fd15316a2d503bf26ab031a61d056e98"
DIMENSIONS = 384
MAX_CHARS = 12000
MAX_BATCH = 16
MODEL_PATH = Path(os.getenv("MODEL_PATH", "/app/model"))
MANIFEST_PATH = Path(os.getenv("MODEL_MANIFEST", "/app/model.manifest.sha256"))
logger = logging.getLogger("mentor.embeddings")
model = None
tokenizer = None
model_lock = threading.Lock()


def verify_manifest() -> None:
    if not MODEL_PATH.is_dir() or not MANIFEST_PATH.is_file():
        raise RuntimeError("e5_model_missing")
    for line in MANIFEST_PATH.read_text(encoding="utf-8").splitlines():
        expected, relative = line.split(maxsplit=1)
        path = MODEL_PATH / relative.removeprefix("./")
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise RuntimeError("e5_model_manifest_mismatch")
    if not (MODEL_PATH / "model.safetensors").is_file():
        raise RuntimeError("e5_safetensors_missing")


def load_model() -> None:
    global model, tokenizer
    if os.getenv("EMBEDDINGS_BACKEND", "real") != "real":
        raise RuntimeError("fixture_backend_forbidden_in_production")
    verify_manifest()
    from transformers import AutoModel, AutoTokenizer

    candidate_tokenizer = AutoTokenizer.from_pretrained(str(MODEL_PATH), local_files_only=True, trust_remote_code=False)
    candidate = AutoModel.from_pretrained(str(MODEL_PATH), local_files_only=True, trust_remote_code=False)
    candidate.eval()
    if int(candidate.config.hidden_size) != DIMENSIONS:
        raise RuntimeError("e5_dimension_invalid")
    model = candidate
    tokenizer = candidate_tokenizer
    logger.info("embedding_model_loaded model_id=%s revision=%s dimensions=%s", MODEL_ID, MODEL_REVISION, DIMENSIONS)


def encode(texts: list[str], prefix: str) -> tuple[list[list[float]], bool]:
    if not texts or len(texts) > MAX_BATCH or prefix not in {"query:", "passage:"}:
        raise ValueError("embedding_request_invalid")
    truncated = [text[:MAX_CHARS] for text in texts]
    was_truncated = any(len(text) > MAX_CHARS for text in texts)
    if any(not text.strip() for text in truncated):
        raise ValueError("embedding_input_empty")
    with model_lock:
        import torch

        encoded = tokenizer([f"{prefix} {text}" for text in truncated], padding=True, truncation=True, max_length=512, return_tensors="pt")
        with torch.no_grad():
            output = model(**encoded).last_hidden_state
        mask = encoded["attention_mask"].unsqueeze(-1).expand(output.size()).float()
        vectors = (output * mask).sum(1) / torch.clamp(mask.sum(1), min=1e-9)
        vectors = torch.nn.functional.normalize(vectors, p=2, dim=1)
    result = [[float(value) for value in vector] for vector in vectors.tolist()]
    if any(len(vector) != DIMENSIONS or not all(math.isfinite(value) for value in vector) for vector in result):
        raise RuntimeError("embedding_output_invalid")
    return result, was_truncated


class Handler(BaseHTTPRequestHandler):
    server_version = "mentor-embeddings/0.2"

    def do_GET(self) -> None:  # noqa: N802
        if self.path != "/health":
            self.send_error(404)
            return
        self._json(200, {"status": "ok", "backend": "e5-real", "model_id": MODEL_ID, "revision": MODEL_REVISION, "dimensions": DIMENSIONS})

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/embed":
            self.send_error(404)
            return
        started = time.perf_counter()
        try:
            length = int(self.headers.get("content-length", "0"))
            if length <= 0 or length > 256 * 1024:
                raise ValueError("payload_too_large")
            body = json.loads(self.rfile.read(length))
            texts = body.get("texts")
            prefix = body.get("prefix", "passage:")
            if not isinstance(texts, list) or any(not isinstance(text, str) for text in texts):
                raise ValueError("embedding_request_invalid")
            vectors, truncated = encode(texts, prefix)
            self._json(200, {"backend": "e5-real", "model_id": MODEL_ID, "revision": MODEL_REVISION, "dimensions": DIMENSIONS, "vectors": vectors, "truncated": truncated, "duration_ms": int((time.perf_counter() - started) * 1000)})
        except (ValueError, json.JSONDecodeError):
            self._json(422, {"detail": "embedding_request_invalid"})
        except Exception:
            logger.exception("embedding_failed")
            self._json(503, {"detail": "embedding_unavailable"})

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
    logging.basicConfig(level=logging.INFO, format='{"level":"%(levelname)s","message":"%(message)s"}')
    load_model()
    ThreadingHTTPServer(("0.0.0.0", 8090), Handler).serve_forever()


if __name__ == "__main__":
    main()
