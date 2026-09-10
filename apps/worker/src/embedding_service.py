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
MODEL_PATH = Path(os.getenv("MODEL_PATH", "/app/model-cpu"))
MANIFEST_PATH = Path(os.getenv("MODEL_MANIFEST", "/app/model-cpu.manifest.sha256"))
logger = logging.getLogger("mentor.embeddings")
model = None
tokenizer = None
runtime = None
model_lock = threading.Lock()


def verify_manifest() -> None:
    if not MODEL_PATH.is_dir() or not MANIFEST_PATH.is_file():
        raise RuntimeError("e5_model_missing")
    for line in MANIFEST_PATH.read_text(encoding="utf-8").splitlines():
        expected, relative = line.split(maxsplit=1)
        path = MODEL_PATH / relative.removeprefix("./")
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise RuntimeError("e5_model_manifest_mismatch")
    if not (MODEL_PATH / "model.onnx").is_file():
        raise RuntimeError("e5_onnx_missing")


def load_model() -> None:
    global model, tokenizer, runtime
    if os.getenv("EMBEDDINGS_BACKEND", "real") != "real":
        raise RuntimeError("fixture_backend_forbidden_in_production")
    verify_manifest()
    import onnxruntime as ort
    from tokenizers import Tokenizer

    candidate_tokenizer = Tokenizer.from_file(str(MODEL_PATH / "tokenizer.json"))
    candidate_tokenizer.enable_truncation(max_length=512)
    candidate_runtime = ort.InferenceSession(
        str(MODEL_PATH / "model.onnx"),
        providers=["CPUExecutionProvider"],
        sess_options=ort.SessionOptions(),
    )
    output_shape = candidate_runtime.get_outputs()[0].shape
    if output_shape[-1] not in {DIMENSIONS, "384"}:
        raise RuntimeError("e5_dimension_invalid")
    model = candidate_runtime
    tokenizer = candidate_tokenizer
    runtime = "onnx-int8-cpu"
    logger.info("embedding_model_loaded model_id=%s revision=%s dimensions=%s runtime=%s", MODEL_ID, MODEL_REVISION, DIMENSIONS, runtime)


def encode(texts: list[str], prefix: str) -> tuple[list[list[float]], bool]:
    if not texts or len(texts) > MAX_BATCH or prefix not in {"query:", "passage:"}:
        raise ValueError("embedding_request_invalid")
    truncated = [text[:MAX_CHARS] for text in texts]
    was_truncated = any(len(text) > MAX_CHARS for text in texts)
    if any(not text.strip() for text in truncated):
        raise ValueError("embedding_input_empty")
    with model_lock:
        import numpy as np
        encodings = [tokenizer.encode(f"{prefix} {text}") for text in truncated]
        max_length = max(len(item.ids) for item in encodings)
        input_ids = np.zeros((len(encodings), max_length), dtype=np.int64)
        attention_mask = np.zeros_like(input_ids)
        for index, encoding in enumerate(encodings):
            input_ids[index, : len(encoding.ids)] = encoding.ids
            attention_mask[index, : len(encoding.ids)] = 1
        output = model.run(None, {"input_ids": input_ids, "attention_mask": attention_mask})[0]
        mask = attention_mask[..., None].astype(np.float32)
        vectors = (output * mask).sum(1) / np.clip(mask.sum(1), 1e-9, None)
        vectors = vectors / np.linalg.norm(vectors, axis=1, keepdims=True)
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
        self._json(200, {"status": "ok", "backend": "e5-real", "runtime": runtime, "model_id": MODEL_ID, "revision": MODEL_REVISION, "dimensions": DIMENSIONS})

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
            self._json(200, {"backend": "e5-real", "runtime": runtime, "model_id": MODEL_ID, "revision": MODEL_REVISION, "dimensions": DIMENSIONS, "vectors": vectors, "truncated": truncated, "duration_ms": int((time.perf_counter() - started) * 1000)})
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
