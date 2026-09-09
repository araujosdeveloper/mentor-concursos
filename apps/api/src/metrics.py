import threading
from collections import Counter

from fastapi import APIRouter, Depends, Response

from .rate_limit import enforce_internal_rate_limit

router = APIRouter(prefix="/api/internal", tags=["internal"])


class MetricsRegistry:
    """Registro leve com dimensões limitadas a método, rota-modelo e status."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._requests: Counter[tuple[str, str, int]] = Counter()
        self._latency_seconds: Counter[tuple[str, str]] = Counter()
        self._auth_failures = 0
        self._rate_limit_rejections = 0
        self._readiness = 0

    def observe_request(self, method: str, route: str, status_code: int, latency: float) -> None:
        with self._lock:
            self._requests[(method, route, status_code)] += 1
            self._latency_seconds[(method, route)] += latency

    def record_auth_failure(self) -> None:
        with self._lock:
            self._auth_failures += 1

    def record_rate_limit_rejection(self) -> None:
        with self._lock:
            self._rate_limit_rejections += 1

    def set_readiness(self, ready: bool) -> None:
        with self._lock:
            self._readiness = int(ready)

    def render(self) -> str:
        with self._lock:
            lines = [
                "# HELP mentor_api_requests_total Requisições HTTP processadas.",
                "# TYPE mentor_api_requests_total counter",
            ]
            for (method, route, status_code), value in sorted(self._requests.items()):
                labels = f'method="{method}",route="{route}",status="{status_code}"'
                lines.append(f"mentor_api_requests_total{{{labels}}} {value}")
            lines.extend(
                [
                    "# HELP mentor_api_request_latency_seconds_sum Latência HTTP acumulada.",
                    "# TYPE mentor_api_request_latency_seconds_sum counter",
                ]
            )
            for (method, route), value in sorted(self._latency_seconds.items()):
                labels = f'method="{method}",route="{route}"'
                lines.append(f"mentor_api_request_latency_seconds_sum{{{labels}}} {value:.6f}")
            lines.extend(
                [
                    "# HELP mentor_api_auth_failures_total Falhas de autenticação.",
                    "# TYPE mentor_api_auth_failures_total counter",
                    f"mentor_api_auth_failures_total {self._auth_failures}",
                    "# HELP mentor_api_rate_limit_rejections_total Requisições limitadas.",
                    "# TYPE mentor_api_rate_limit_rejections_total counter",
                    f"mentor_api_rate_limit_rejections_total {self._rate_limit_rejections}",
                    "# HELP mentor_api_ready Estado atual do readiness.",
                    "# TYPE mentor_api_ready gauge",
                    f"mentor_api_ready {self._readiness}",
                ]
            )
        return "\n".join(lines) + "\n"

    def reset(self) -> None:
        with self._lock:
            self._requests.clear()
            self._latency_seconds.clear()
            self._auth_failures = 0
            self._rate_limit_rejections = 0
            self._readiness = 0


metrics = MetricsRegistry()


@router.get("/metrics", dependencies=[Depends(enforce_internal_rate_limit)])
async def internal_metrics() -> Response:
    return Response(content=metrics.render(), media_type="text/plain; version=0.0.4")
