import asyncio
from dataclasses import dataclass

import psycopg
import redis

from .config import Settings


@dataclass(frozen=True)
class DependencyStatus:
    postgres: bool
    redis: bool


def _postgres_check(settings: Settings) -> bool:
    try:
        with psycopg.connect(
            host=settings.database_host,
            port=settings.database_port,
            dbname=settings.database_name,
            user=settings.database_user,
            password=settings.database_password,
            connect_timeout=max(1, int(settings.readiness_timeout_seconds)),
        ) as connection:
            return connection.execute("SELECT 1").fetchone() == (1,)
    except psycopg.Error:
        return False


def _redis_check(settings: Settings) -> bool:
    client = redis.Redis(
        host=settings.redis_host,
        port=settings.redis_port,
        password=settings.redis_password,
        socket_connect_timeout=settings.readiness_timeout_seconds,
        socket_timeout=settings.readiness_timeout_seconds,
    )
    try:
        return bool(client.ping())
    except redis.RedisError:
        return False
    finally:
        client.close()


async def check_dependencies(settings: Settings) -> DependencyStatus:
    postgres_ok, redis_ok = await asyncio.gather(
        asyncio.to_thread(_postgres_check, settings),
        asyncio.to_thread(_redis_check, settings),
    )
    return DependencyStatus(postgres=postgres_ok, redis=redis_ok)
