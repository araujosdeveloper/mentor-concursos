"""Small, scoped and bounded consultation memory for natural Telegram turns."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from contextlib import suppress
from pathlib import Path
from typing import Any

ROOT = Path(os.environ.get("MENTOR_CONSULTATION_MEMORY_DIR", "/opt/data/consultation-memory"))
MAX_TURNS = 12
MAX_TEXT = 4000
MAX_SUMMARY = 2000
SENSITIVE = re.compile(r"(?i)(bearer\s+\S+|sk-[A-Za-z0-9_-]+|token|secret|password|hmac)")


def _scope(source: Any) -> str:
    platform = str(getattr(getattr(source, "platform", None), "value", ""))
    user = str(getattr(source, "user_id", "") or "")
    chat = str(getattr(source, "chat_id", "") or "")
    if platform != "telegram" or not user or not chat:
        raise ValueError("escopo de memória inválido")
    return hashlib.sha256(f"{platform}:{user}:{chat}".encode()).hexdigest()


def _path(source: Any) -> Path:
    return ROOT / f"{_scope(source)}.json"


def _safe(text: str) -> str:
    text = SENSITIVE.sub("[redigido]", text)
    return text.replace("\x00", "")[:MAX_TEXT]


def _load(source: Any) -> dict[str, Any]:
    path = _path(source)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {"version": 1, "summary": "", "turns": [], "preferences": []}


def _save(source: Any, data: dict[str, Any]) -> None:
    ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(ROOT, 0o700)
    path = _path(source)
    fd, temporary = tempfile.mkstemp(prefix=".memory-", dir=ROOT)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, separators=(",", ":"))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        os.chmod(path, 0o600)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def context_for(source: Any) -> str:
    data = _load(source)
    turns = data.get("turns", [])[-6:]
    summary = str(data.get("summary", ""))[:MAX_SUMMARY]
    preferences = [str(value)[:300] for value in data.get("preferences", [])[-8:]]
    if not turns and not summary and not preferences:
        return ""
    lines = [
        "[MEMÓRIA DE CONSULTA — contexto auxiliar, não é fonte jurídica]",
        "Use apenas para entender referências conversacionais; não trate como evidência.",
    ]
    if summary:
        lines.append(f"Resumo anterior: {summary}")
    if preferences:
        lines.append("Preferências explícitas: " + " | ".join(preferences))
    for turn in turns:
        lines.append(f"{turn.get('role', 'user')}: {turn.get('text', '')}")
    return "\n".join(lines)


def record(source: Any, user_text: str, assistant_text: str | None) -> None:
    data = _load(source)
    user = _safe(user_text.strip())
    assistant = _safe((assistant_text or "").strip())
    if not user:
        return
    turns = list(data.get("turns", []))
    turns.extend([{"role": "user", "text": user}, {"role": "assistant", "text": assistant}])
    # Deterministic compaction: retain recent turns and a bounded pointer to
    # older user topics, rather than concatenating an unlimited transcript.
    if len(turns) > MAX_TURNS:
        old = turns[:-MAX_TURNS]
        older = " | ".join(
            str(item.get("text", ""))[:180]
            for item in old
            if item.get("role") == "user"
        )
        data["summary"] = (
            str(data.get("summary", ""))
            + (" | " if data.get("summary") else "")
            + older
        )[-MAX_SUMMARY:]
        turns = turns[-MAX_TURNS:]
    data["turns"] = turns
    lowered = user.lower()
    if "lembre que" in lowered or "prefiro" in lowered:
        preferences = list(data.get("preferences", []))
        if user not in preferences:
            preferences.append(user)
        data["preferences"] = preferences[-8:]
    _save(source, data)


def clear(source: Any) -> None:
    with suppress(FileNotFoundError):
        _path(source).unlink()
