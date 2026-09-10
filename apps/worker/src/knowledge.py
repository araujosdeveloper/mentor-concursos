"""Primitivas determinísticas e seguras do pipeline de conhecimento.

O conteúdo é sempre tratado como dado não confiável. Este módulo não executa
texto recebido e não chama internet, Hermes ou qualquer modelo conversacional.
"""

# ruff: noqa: E501

from __future__ import annotations

import hashlib
import math
import re
import unicodedata
import uuid
from dataclasses import dataclass
from pathlib import Path

MAX_BYTES = 50 * 1024 * 1024
MODEL_ID = "intfloat/multilingual-e5-small"
MODEL_REVISION = "fd1525a9fd15316a2d503bf26ab031a61d056e98"
EMBEDDING_DIMENSIONS = 384
CHUNK_ALGORITHM = "headings-paragraphs-v1"


class DocumentRejected(ValueError):
    """Documento inválido ou não permitido pela quarentena."""


@dataclass(frozen=True)
class ValidatedDocument:
    storage_key: str
    sha256: str
    byte_size: int
    mime_type: str
    data: bytes


def safe_storage_key(data: bytes, suffix: str) -> str:
    """Gera chave aleatória, sem incorporar nome enviado pelo cliente."""
    digest = hashlib.sha256(data).hexdigest()
    return f"{uuid.uuid4().hex}/{digest}{suffix}"


def validate_document(data: bytes, declared_mime: str | None, filename: str) -> ValidatedDocument:
    if not data or len(data) > MAX_BYTES:
        raise DocumentRejected("document_size_invalid")
    if ".." in Path(filename).parts or Path(filename).is_absolute() or "\\" in filename:
        raise DocumentRejected("path_traversal")
    suffix = Path(filename).suffix.lower()
    allowed = {".pdf": "application/pdf", ".txt": "text/plain", ".md": "text/markdown"}
    mime = allowed.get(suffix)
    if mime is None or declared_mime not in (None, mime):
        raise DocumentRejected("mime_not_allowed")
    if mime == "application/pdf" and not data.startswith(b"%PDF-"):
        raise DocumentRejected("magic_bytes_invalid")
    if mime != "application/pdf":
        try:
            data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise DocumentRejected("utf8_invalid") from exc
        if b"\x00" in data:
            raise DocumentRejected("binary_content")
    if b"<script" in data.lower() or b"#!" in data[:128]:
        raise DocumentRejected("active_content")
    return ValidatedDocument(safe_storage_key(data, suffix), hashlib.sha256(data).hexdigest(), len(data), mime, data)


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFC", text).replace("\r\n", "\n").replace("\r", "\n")
    text = "\n".join(re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines())
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def detect_prompt_injection(text: str) -> bool:
    patterns = (r"ignore\s+(all|previous)\s+instructions", r"system\s+prompt", r"execute\s+this\s+command")
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)


def chunk_text(text: str, max_chars: int = 1400, overlap: int = 120) -> list[dict[str, object]]:
    if max_chars < 200 or overlap < 0 or overlap >= max_chars:
        raise ValueError("chunk_configuration_invalid")
    normalized = normalize_text(text)
    if not normalized:
        return []
    paragraphs = [part.strip() for part in re.split(r"\n{2,}", normalized) if part.strip()]
    chunks: list[dict[str, object]] = []
    current = ""
    for paragraph in paragraphs:
        if current and len(current) + len(paragraph) + 2 > max_chars:
            chunks.append(current)
            tail = current[-overlap:] if overlap else ""
            current = f"{tail}\n{paragraph}".strip()
        else:
            current = f"{current}\n\n{paragraph}".strip()
    if current:
        chunks.append(current)
    result = []
    for ordinal, value in enumerate(chunks):
        value = normalize_text(value)
        result.append({
            "ordinal": ordinal,
            "text": value,
            "normalized_text": value,
            "content_sha256": hashlib.sha256(value.encode()).hexdigest(),
            "character_count": len(value),
            "token_count": max(1, len(value.split())),
            "prompt_injection_suspected": detect_prompt_injection(value),
            "algorithm": CHUNK_ALGORITHM,
        })
    return result


def hash_embedding(text: str, prefix: str = "passage:") -> list[float]:
    """Deterministic offline fallback used by fixtures and contract tests.

    Production model wiring uses the same E5 prefixes and contract. The service
    rejects non-finite vectors and always returns normalized 384 dimensions.
    """
    values = [0.0] * EMBEDDING_DIMENSIONS
    tokens = (prefix + text).lower().split()
    for token in tokens:
        digest = hashlib.sha256(token.encode()).digest()
        for offset in range(0, len(digest), 2):
            index = int.from_bytes(digest[offset:offset + 2], "big") % EMBEDDING_DIMENSIONS
            values[index] += 1.0 if digest[offset] & 1 else -1.0
    norm = math.sqrt(sum(item * item for item in values)) or 1.0
    result = [item / norm for item in values]
    if len(result) != EMBEDDING_DIMENSIONS or not all(math.isfinite(item) for item in result):
        raise ValueError("embedding_invalid")
    return result
