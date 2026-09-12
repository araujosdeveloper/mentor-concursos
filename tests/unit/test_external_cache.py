from __future__ import annotations

import redis

from apps.external.cache import TransientCache


class FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, bytes] = {}

    def get(self, key: str) -> bytes | None:
        return self.store.get(key)

    def set(self, key: str, value: str, ex: int | None = None) -> None:
        self.store[key] = value.encode()


class BrokenRedis:
    def get(self, _key: str) -> None:
        raise redis.RedisError("down")

    def set(self, _key: str, _value: str, ex: int | None = None) -> None:
        raise redis.RedisError("down")


def _cache(monkeypatch, client) -> TransientCache:
    monkeypatch.setattr("apps.external.cache.redis.Redis", lambda **_kwargs: client)
    return TransientCache(host="h", port=1, password="p", ttl_seconds=60)


def test_set_then_get_roundtrip(monkeypatch) -> None:
    cache = _cache(monkeypatch, FakeRedis())
    cache.set("k", "v")
    assert cache.get("k") == "v"


def test_missing_key_returns_none(monkeypatch) -> None:
    assert _cache(monkeypatch, FakeRedis()).get("missing") is None


def test_redis_failure_is_fail_open(monkeypatch) -> None:
    cache = _cache(monkeypatch, BrokenRedis())
    assert cache.get("k") is None
    cache.set("k", "v")
