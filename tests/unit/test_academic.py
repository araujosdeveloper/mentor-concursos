from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi import HTTPException

from apps.api.src.academic import (
    AcademicUser,
    CycleCreate,
    GoalCreate,
    SessionStart,
    _fingerprint,
    _idempotency_key,
    _idempotency_scope,
    _session_timestamp,
    _utc,
    get_goal,
)
from apps.api.src.config import Settings


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


def test_session_timestamps_cannot_be_in_the_future() -> None:
    with pytest.raises(HTTPException, match="Timestamp futuro"):
        _session_timestamp(datetime.now(UTC) + timedelta(minutes=1))


def test_idempotency_scope_isolated_by_user_and_operation() -> None:
    from starlette.requests import Request

    request = Request({"type": "http", "method": "POST", "path": "/api/v1/goals", "headers": []})
    first = AcademicUser(uuid4(), 1, "A")
    second = AcademicUser(uuid4(), 2, "B")
    assert _idempotency_scope(request, first) != _idempotency_scope(request, second)
    assert _idempotency_scope(request, first).startswith("POST:/api/v1/goals:")


def test_cross_user_resource_lookup_returns_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeResult:
        def fetchone(self):
            return None

    class FakeConnection:
        def __init__(self):
            self.params = None

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, _query, params):
            self.params = params
            return FakeResult()

    goal_id = uuid4()
    user_id = uuid4()
    connection = FakeConnection()
    monkeypatch.setattr("apps.api.src.academic._connect", lambda _settings: connection)
    with pytest.raises(HTTPException) as error:
        get_goal(goal_id, AcademicUser(user_id, 1, "Roberto"), Settings())
    assert error.value.status_code == 404
    assert connection.params == (goal_id, user_id)
