import asyncio

from fastapi import Response

from apps.api.src import health
from apps.api.src.main import app


def test_live_has_stable_payload() -> None:
    result = asyncio.run(health.live())
    assert result.model_dump() == {"status": "ok", "service": "mentor-concursos-api"}


def test_health_routes_are_registered() -> None:
    paths = {route.path for route in app.routes}
    assert "/api/health/live" in paths
    assert "/api/health/ready" in paths


def test_ready_when_dependencies_are_available(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    async def available(*_args, **_kwargs) -> bool:  # type: ignore[no-untyped-def]
        return True

    monkeypatch.setattr(health, "_tcp_check", available)
    response = Response()
    result = asyncio.run(health.ready(response))
    assert response.status_code == 200
    assert result.model_dump() == {
        "status": "ready",
        "service": "mentor-concursos-api",
        "checks": {"postgres": "ok", "redis": "ok"},
    }


def test_ready_fails_closed(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    async def unavailable(*_args, **_kwargs) -> bool:  # type: ignore[no-untyped-def]
        return False

    monkeypatch.setattr(health, "_tcp_check", unavailable)
    response = Response()
    result = asyncio.run(health.ready(response))
    assert response.status_code == 503
    assert result.status == "not_ready"
