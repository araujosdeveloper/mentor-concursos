import asyncio

import pytest
import redis
from fastapi import HTTPException
from starlette.requests import Request

from apps.api.src import rate_limit
from apps.api.src.config import Settings


def make_request() -> Request:
    return Request({"type": "http", "method": "GET", "path": "/api/internal/auth-check"})


def test_rate_limit_allows_within_policy(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    async def consume(*_args, **_kwargs) -> int:  # type: ignore[no-untyped-def]
        return 2

    monkeypatch.setattr(rate_limit, "_consume", consume)
    settings = Settings(rate_limit_requests=2)
    result = asyncio.run(rate_limit.enforce_internal_rate_limit(make_request(), None, settings))
    assert result is None


def test_rate_limit_returns_uniform_429(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    async def consume(*_args, **_kwargs) -> int:  # type: ignore[no-untyped-def]
        return 3

    monkeypatch.setattr(rate_limit, "_consume", consume)
    with pytest.raises(HTTPException) as error:
        asyncio.run(
            rate_limit.enforce_internal_rate_limit(
                make_request(),
                None,
                Settings(rate_limit_requests=2),
            )
        )
    assert error.value.status_code == 429
    assert error.value.detail == "Limite de requisições excedido"
    assert error.value.headers == {"Retry-After": "60"}


def test_protected_route_fails_closed_without_redis(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    async def consume(*_args, **_kwargs) -> int:  # type: ignore[no-untyped-def]
        raise redis.RedisError("indisponível")

    monkeypatch.setattr(rate_limit, "_consume", consume)
    with pytest.raises(HTTPException) as error:
        asyncio.run(
            rate_limit.enforce_internal_rate_limit(
                make_request(),
                None,
                Settings(rate_limit_requests=2),
            )
        )
    assert error.value.status_code == 503
    assert error.value.detail == "Serviço temporariamente indisponível"
