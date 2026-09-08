from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from apps.api.src.auth import require_service_token
from apps.api.src.config import Settings


def settings_with_token(path: Path) -> Settings:
    return Settings(service_token_file=path)


def test_missing_token_is_rejected(tmp_path: Path) -> None:
    token_file = tmp_path / "service-token"
    token_file.write_text("a" * 64, encoding="utf-8")
    with pytest.raises(HTTPException) as error:
        require_service_token(None, settings_with_token(token_file))
    assert error.value.status_code == 401
    assert error.value.detail == "Não autorizado"


def test_invalid_token_is_rejected(tmp_path: Path) -> None:
    token_file = tmp_path / "service-token"
    token_file.write_text("a" * 64, encoding="utf-8")
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="b" * 64)
    with pytest.raises(HTTPException) as error:
        require_service_token(credentials, settings_with_token(token_file))
    assert error.value.status_code == 401
    assert error.value.detail == "Não autorizado"


def test_valid_token_is_accepted(tmp_path: Path) -> None:
    token = "a" * 64
    token_file = tmp_path / "service-token"
    token_file.write_text(token, encoding="utf-8")
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    assert require_service_token(credentials, settings_with_token(token_file)) is None
