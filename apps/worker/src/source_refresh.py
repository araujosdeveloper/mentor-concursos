"""Persistência transacional da verificação de uma fonte oficial."""

# ruff: noqa: E501

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any


def apply_update(connection: Any, *, source_id: str, acquisition: Any, storage_root: Path) -> str:
    """Registra 304/hash igual ou cria uma única versão em quarentena.

    O chamador deve fornecer uma conexão transacional. O advisory lock evita
    duas atualizações simultâneas da mesma fonte sem bloquear outras fontes.
    """
    connection.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (f"source-refresh:{source_id}",))
    current = connection.execute(
        "SELECT id, sha256, status FROM mentor_concursos.knowledge_source_versions "
        "WHERE source_id=%s ORDER BY created_at DESC LIMIT 1 FOR UPDATE", (source_id,)
    ).fetchone()
    if acquisition.status == 304:
        connection.execute(
            "UPDATE mentor_concursos.knowledge_sources SET last_checked_at=CURRENT_TIMESTAMP, etag=%s, last_modified=%s WHERE id=%s",
            (acquisition.etag, acquisition.last_modified, source_id),
        )
        return "not_modified"
    if current and current[1] == acquisition.sha256:
        connection.execute(
            "UPDATE mentor_concursos.knowledge_sources SET last_checked_at=CURRENT_TIMESTAMP, etag=%s, last_modified=%s WHERE id=%s",
            (acquisition.etag, acquisition.last_modified, source_id),
        )
        return "unchanged"
    digest = hashlib.sha256(acquisition.data).hexdigest()
    if digest != acquisition.sha256:
        raise ValueError("acquisition_hash_mismatch")
    target = storage_root / "quarantine" / digest
    target.mkdir(parents=True, exist_ok=True)
    artifact = target / f"{digest}.bin"
    if not artifact.exists():
        artifact.write_bytes(acquisition.data)
        artifact.chmod(0o600)
    connection.execute(
        "INSERT INTO mentor_concursos.knowledge_source_versions "
        "(source_id,version_label,supersedes_version_id,sha256,mime_type,byte_size,storage_key,status,artifact_url,quarantine_checked_at) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,'quarantined',%s,CURRENT_TIMESTAMP) "
        "ON CONFLICT (source_id,sha256) DO NOTHING",
        (source_id, acquisition.sha256, current[0] if current else None, acquisition.sha256,
         acquisition.content_type.split(";", 1)[0], len(acquisition.data),
         f"quarantine/{digest}/{digest}.bin", acquisition.url),
    )
    connection.execute(
        "UPDATE mentor_concursos.knowledge_sources SET last_checked_at=CURRENT_TIMESTAMP, etag=%s, last_modified=%s WHERE id=%s",
        (acquisition.etag, acquisition.last_modified, source_id),
    )
    return "changed_quarantine"
