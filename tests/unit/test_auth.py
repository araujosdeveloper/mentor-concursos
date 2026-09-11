import hashlib
import hmac
import json
import time
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from apps.api.src.auth import require_service_token, signed_context_user_id
from apps.api.src.config import Settings


def test_production_rejects_unsigned_context_configuration() -> None:
    with pytest.raises(ValueError, match="REQUIRE_SIGNED_CONTEXT"):
        Settings(app_env="production", require_signed_context=False)


def test_development_allows_legacy_unsigned_context_configuration() -> None:
    settings = Settings(app_env="development", require_signed_context=False)
    assert settings.require_signed_context is False


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


def _request(headers: dict[str, str]):
    from starlette.requests import Request

    return Request({
        "type": "http", "method": "GET", "path": "/api/v1/users/me",
        "headers": [(key.lower().encode(), value.encode()) for key, value in headers.items()],
    })


def _signed_headers(
    key: bytes, timestamp: int | None = None, nonce: str = "a" * 32
) -> dict[str, str]:
    context = {
        "telegram_user_id": 5710991322,
        "chat_id": 5710991322,
        "ts": int(time.time()) if timestamp is None else timestamp,
        "nonce": nonce,
    }
    canonical = f"{context['telegram_user_id']}.{context['chat_id']}.{context['ts']}.{nonce}"
    return {
        "X-Hermes-Context": json.dumps(context, separators=(",", ":")),
        "X-Hermes-Signature": hmac.new(key, canonical.encode(), hashlib.sha256).hexdigest(),
        "X-Telegram-User-ID": str(context["telegram_user_id"]),
    }


def test_signed_context_required_rejects_legacy_header(tmp_path: Path) -> None:
    settings = Settings(context_hmac_key_file=tmp_path / "hmac", require_signed_context=True)
    with pytest.raises(HTTPException) as error:
        signed_context_user_id(_request({"X-Telegram-User-ID": "5710991322"}), settings)
    assert error.value.status_code == 401


def test_signed_context_validates_and_consumes_nonce(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    key = b"k" * 32
    key_file = tmp_path / "hmac"
    key_file.write_bytes(key)

    class FakeRedis:
        accepted_global = True

        def __init__(self, **_kwargs):
            pass

        def set(self, *_args, **_kwargs):
            value, FakeRedis.accepted_global = FakeRedis.accepted_global, False
            return value

        def close(self):
            pass

    monkeypatch.setattr("apps.api.src.auth.redis.Redis", FakeRedis)
    settings = Settings(context_hmac_key_file=key_file, require_signed_context=True)
    headers = _signed_headers(key)
    assert signed_context_user_id(_request(headers), settings) == 5710991322
    with pytest.raises(HTTPException) as error:
        signed_context_user_id(_request(headers), settings)
    assert error.value.status_code == 401


def test_signed_context_expired_is_rejected(tmp_path: Path) -> None:
    key = b"k" * 32
    key_file = tmp_path / "hmac"
    key_file.write_bytes(key)
    settings = Settings(context_hmac_key_file=key_file, require_signed_context=True)
    with pytest.raises(HTTPException) as error:
        signed_context_user_id(_request(_signed_headers(key, int(time.time()) - 61)), settings)
    assert error.value.status_code == 401


def test_payload_tampered_after_signing_is_rejected(tmp_path: Path) -> None:
    key = b"k" * 32
    key_file = tmp_path / "hmac"
    key_file.write_bytes(key)
    settings = Settings(context_hmac_key_file=key_file, require_signed_context=True)
    headers = _signed_headers(key)
    tampered = json.loads(headers["X-Hermes-Context"])
    tampered["telegram_user_id"] = 999999999
    headers["X-Hermes-Context"] = json.dumps(tampered, separators=(",", ":"))
    with pytest.raises(HTTPException) as error:
        signed_context_user_id(_request(headers), settings)
    assert error.value.status_code == 401
