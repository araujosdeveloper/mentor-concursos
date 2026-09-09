import time
from typing import Annotated

import redis.asyncio as redis_async
from fastapi import Depends, HTTPException, Request, status

from .auth import require_service_token
from .config import Settings, get_settings

RATE_LIMIT_UNAVAILABLE = HTTPException(
    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
    detail="Serviço temporariamente indisponível",
)

SCRIPT = """
local current = redis.call('INCR', KEYS[1])
if current == 1 then
  redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return current
"""


async def _consume(settings: Settings, bucket: str, now: float) -> int:
    window = settings.rate_limit_window_seconds
    window_id = int(now // window)
    key = f"mentor:rate-limit:{bucket}:{window_id}"
    client = redis_async.Redis(
        host=settings.redis_host,
        port=settings.redis_port,
        password=settings.redis_password,
        socket_connect_timeout=settings.readiness_timeout_seconds,
        socket_timeout=settings.readiness_timeout_seconds,
    )
    try:
        result = await client.eval(SCRIPT, 1, key, window)
        return int(result)
    finally:
        await client.aclose()


async def enforce_internal_rate_limit(
    request: Request,
    _: Annotated[None, Depends(require_service_token)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    route = request.scope.get("route")
    bucket = getattr(route, "path", "/api/internal")
    try:
        count = await _consume(settings, bucket, time.time())
    except (OSError, redis_async.RedisError):
        raise RATE_LIMIT_UNAVAILABLE from None
    if count > settings.rate_limit_requests:
        from .metrics import metrics

        metrics.record_rate_limit_rejection()
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Limite de requisições excedido",
            headers={"Retry-After": str(settings.rate_limit_window_seconds)},
        )
