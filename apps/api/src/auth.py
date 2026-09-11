import hashlib
import hmac
import json
import logging
import re
import secrets
import time
from contextlib import suppress
from typing import Annotated

import redis
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import Settings, get_settings

bearer = HTTPBearer(auto_error=False)
UNAUTHORIZED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Não autorizado",
    headers={"WWW-Authenticate": "Bearer"},
)

_CONTEXT_LOGGER = logging.getLogger("mentor.auth.context")
_NONCE_PATTERN = re.compile(r"^[0-9a-f]{32}$")


def require_service_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    try:
        expected = settings.service_token_file.read_text(encoding="utf-8").strip()
    except OSError:
        from .metrics import metrics

        metrics.record_auth_failure()
        raise UNAUTHORIZED from None

    supplied = credentials.credentials if credentials and credentials.scheme == "Bearer" else ""
    if not expected or not secrets.compare_digest(supplied.encode(), expected.encode()):
        from .metrics import metrics

        metrics.record_auth_failure()
        raise UNAUTHORIZED


def signed_context_user_id(request, settings: Settings) -> int | None:
    """Validate the optional Hermes identity envelope and consume its nonce.

    A missing envelope remains compatible while REQUIRE_SIGNED_CONTEXT is false.
    Once present, however, the envelope is always validated; an invalid envelope
    is never silently downgraded to the legacy header path.
    """
    raw_context = request.headers.get("X-Hermes-Context")
    raw_signature = request.headers.get("X-Hermes-Signature")
    if not raw_context and not raw_signature:
        if settings.require_signed_context:
            raise UNAUTHORIZED
        return None
    if not raw_context or not raw_signature or not re.fullmatch(r"[0-9a-f]{64}", raw_signature):
        raise UNAUTHORIZED
    try:
        context = json.loads(raw_context)
        if set(context) != {"telegram_user_id", "chat_id", "ts", "nonce"}:
            raise ValueError
        telegram_user_id = context["telegram_user_id"]
        chat_id = context["chat_id"]
        timestamp = context["ts"]
        nonce = context["nonce"]
        if isinstance(telegram_user_id, bool) or isinstance(chat_id, bool):
            raise ValueError
        telegram_user_id = int(telegram_user_id)
        chat_id = int(chat_id)
        timestamp = int(timestamp)
        if not isinstance(nonce, str) or not _NONCE_PATTERN.fullmatch(nonce):
            raise ValueError
        canonical = f"{telegram_user_id}.{chat_id}.{timestamp}.{nonce}".encode()
        key = settings.context_hmac_key_file.read_bytes().strip()
        expected = hmac.new(key, canonical, hashlib.sha256).hexdigest()
        if not key or not hmac.compare_digest(expected, raw_signature):
            raise ValueError
        if abs(time.time() - timestamp) > settings.signed_context_max_age_seconds:
            raise ValueError
    except (OSError, TypeError, ValueError, json.JSONDecodeError, OverflowError):
        raise UNAUTHORIZED from None

    # Redis is the shared replay barrier. Any failure is fail-closed.
    client = redis.Redis(
        host=settings.redis_host,
        port=settings.redis_port,
        password=settings.redis_password,
        socket_connect_timeout=settings.readiness_timeout_seconds,
        socket_timeout=settings.readiness_timeout_seconds,
    )
    try:
        accepted = client.set(
            f"mentor:hermes-context:nonce:{nonce}",
            "1",
            nx=True,
            ex=settings.signed_context_replay_ttl_seconds,
        )
    except (OSError, redis.RedisError):
        raise UNAUTHORIZED from None
    finally:
        with suppress(OSError):
            client.close()
    if not accepted:
        raise UNAUTHORIZED

    legacy_header = request.headers.get("X-Telegram-User-ID")
    if legacy_header is not None and legacy_header != str(telegram_user_id):
        _CONTEXT_LOGGER.warning("signed_context_header_discrepancy")
    return telegram_user_id
