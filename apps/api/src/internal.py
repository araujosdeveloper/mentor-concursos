from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from .rate_limit import enforce_internal_rate_limit

router = APIRouter(prefix="/api/internal", tags=["internal"])


class AuthCheckResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: str = "mentor-concursos-api"


@router.get("/auth-check", response_model=AuthCheckResponse)
async def auth_check(
    _: Annotated[None, Depends(enforce_internal_rate_limit)],
) -> AuthCheckResponse:
    """Valida exclusivamente o contrato de autenticação serviço-a-serviço."""
    return AuthCheckResponse()
