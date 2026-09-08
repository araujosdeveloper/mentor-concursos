import asyncio
from typing import Literal

from fastapi import APIRouter, Response, status
from pydantic import BaseModel

from .config import get_settings

router = APIRouter(prefix="/api/health", tags=["health"])


class LiveResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: str = "mentor-concursos-api"


class ReadyResponse(BaseModel):
    status: Literal["ready", "not_ready"]
    service: str = "mentor-concursos-api"
    checks: dict[str, Literal["ok", "error"]]


async def _tcp_check(host: str, port: int, timeout: float) -> bool:
    try:
        _, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout)
        writer.close()
        await writer.wait_closed()
    except (OSError, TimeoutError):
        return False
    return True


@router.get("/live", response_model=LiveResponse)
async def live() -> LiveResponse:
    return LiveResponse()


@router.get("/ready", response_model=ReadyResponse)
async def ready(response: Response) -> ReadyResponse:
    settings = get_settings()
    database_ok, redis_ok = await asyncio.gather(
        _tcp_check(
            settings.database_host,
            settings.database_port,
            settings.readiness_timeout_seconds,
        ),
        _tcp_check(settings.redis_host, settings.redis_port, settings.readiness_timeout_seconds),
    )
    checks: dict[str, Literal["ok", "error"]] = {
        "postgres": "ok" if database_ok else "error",
        "redis": "ok" if redis_ok else "error",
    }
    if not all((database_ok, redis_ok)):
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return ReadyResponse(status="not_ready", checks=checks)
    return ReadyResponse(status="ready", checks=checks)
