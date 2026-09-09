from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi import HTTPException

from apps.api.src.academic import (
    CycleCreate,
    GoalCreate,
    SessionStart,
    _fingerprint,
    _idempotency_key,
    _utc,
)


def test_strict_schemas_reject_unknown_fields() -> None:
    with pytest.raises(ValueError):
        GoalCreate(name="objetivo", horizon="seis meses", weekly_minutes=600, unknown="x")


def test_cycle_requires_positive_interval() -> None:
    with pytest.raises(ValueError):
        CycleCreate(
            name="ciclo",
            starts_at=datetime(2026, 1, 2, tzinfo=UTC),
            ends_at=datetime(2026, 1, 1, tzinfo=UTC),
            weekly_minutes=600,
        )


def test_datetime_is_persisted_as_utc() -> None:
    value = _utc(datetime(2026, 1, 1, 12, 0))
    assert value.tzinfo == UTC


def test_idempotency_key_and_fingerprint_are_deterministic() -> None:
    payload = {"goal_id": str(uuid4()), "minutes": 30}
    assert _fingerprint(payload) == _fingerprint({"minutes": 30, "goal_id": payload["goal_id"]})
    assert _idempotency_key("phase2b-001") == "phase2b-001"
    with pytest.raises(HTTPException):
        _idempotency_key("short")


def test_session_input_has_no_client_duration() -> None:
    session = SessionStart(goal_id=uuid4(), subject_id=uuid4())
    assert not hasattr(session, "net_duration_seconds")
