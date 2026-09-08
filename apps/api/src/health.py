from typing import Literal

from fastapi import APIRouter, Response, status
from pydantic import BaseModel

from .config import get_settings
from .dependencies import check_dependencies

router = APIRouter(prefix="/api/health", tags=["health"])


class LiveResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: str = "mentor-concursos-api"


class ReadyResponse(BaseModel):
    status: Literal["ready", "not_ready"]
    service: str = "mentor-concursos-api"
    checks: dict[str, Literal["ok", "error"]]


@router.get("/live", response_model=LiveResponse)
async def live() -> LiveResponse:
    return LiveResponse()


@router.get("/ready", response_model=ReadyResponse)
async def ready(response: Response) -> ReadyResponse:
    settings = get_settings()
    dependency_status = await check_dependencies(settings)
    checks: dict[str, Literal["ok", "error"]] = {
        "postgres": "ok" if dependency_status.postgres else "error",
        "redis": "ok" if dependency_status.redis else "error",
    }
    if not all((dependency_status.postgres, dependency_status.redis)):
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return ReadyResponse(status="not_ready", checks=checks)
    return ReadyResponse(status="ready", checks=checks)
