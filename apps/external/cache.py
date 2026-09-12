"""Cache transitório e efêmero do conteúdo bruto buscado externamente (ADR-020)."""

from __future__ import annotations

from contextlib import suppress

import redis

_PREFIX = "external:content:"


class TransientCache:
    """Cache fail-open de curta duração; ausência de Redis não bloqueia a consulta."""

    def __init__(self, *, host: str, port: int, password: str, ttl_seconds: int = 300) -> None:
        self._ttl = ttl_seconds
        self._client = redis.Redis(
            host=host,
            port=port,
            password=password,
            socket_connect_timeout=1.0,
            socket_timeout=1.0,
        )

    def get(self, key: str) -> str | None:
        try:
            value = self._client.get(_PREFIX + key)
        except redis.RedisError:
            return None
        return value.decode("utf-8") if value is not None else None

    def set(self, key: str, value: str) -> None:
        with suppress(redis.RedisError):
            self._client.set(_PREFIX + key, value, ex=self._ttl)
