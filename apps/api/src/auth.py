import secrets
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import Settings, get_settings

bearer = HTTPBearer(auto_error=False)
UNAUTHORIZED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Não autorizado",
    headers={"WWW-Authenticate": "Bearer"},
)


def require_service_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    try:
        expected = settings.service_token_file.read_text(encoding="utf-8").strip()
    except OSError:
        raise UNAUTHORIZED from None

    supplied = credentials.credentials if credentials and credentials.scheme == "Bearer" else ""
    if not expected or not secrets.compare_digest(supplied.encode(), expected.encode()):
        raise UNAUTHORIZED
