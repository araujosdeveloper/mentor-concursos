from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from .auth import require_service_token

router = APIRouter(prefix="/api/internal", tags=["internal"])


class AuthCheckResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: str = "mentor-concursos-api"


@router.get("/auth-check", response_model=AuthCheckResponse)
async def auth_check(_: Annotated[None, Depends(require_service_token)]) -> AuthCheckResponse:
    """Valida exclusivamente o contrato de autenticação serviço-a-serviço."""
    return AuthCheckResponse()
