import asyncio

from fastapi import Response

from apps.api.src import health
from apps.api.src.dependencies import DependencyStatus
from apps.api.src.main import app


def test_live_has_stable_payload() -> None:
    result = asyncio.run(health.live())
    assert result.model_dump() == {"status": "ok", "service": "mentor-concursos-api"}


def test_health_routes_are_registered() -> None:
    paths = {route.path for route in app.routes}
    assert "/api/health/live" in paths
    assert "/api/health/ready" in paths
    assert "/api/internal/auth-check" in paths


def test_ready_when_dependencies_are_available(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    async def available(*_args, **_kwargs) -> DependencyStatus:  # type: ignore[no-untyped-def]
        return DependencyStatus(postgres=True, redis=True)

    monkeypatch.setattr(health, "check_dependencies", available)
    response = Response()
    result = asyncio.run(health.ready(response))
    assert response.status_code == 200
    assert result.model_dump() == {
        "status": "ready",
        "service": "mentor-concursos-api",
        "checks": {"postgres": "ok", "redis": "ok"},
    }


def test_ready_fails_closed(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    async def unavailable(*_args, **_kwargs) -> DependencyStatus:  # type: ignore[no-untyped-def]
        return DependencyStatus(postgres=False, redis=True)

    monkeypatch.setattr(health, "check_dependencies", unavailable)
    response = Response()
    result = asyncio.run(health.ready(response))
    assert response.status_code == 503
    assert result.status == "not_ready"
    assert result.checks == {"postgres": "error", "redis": "ok"}
