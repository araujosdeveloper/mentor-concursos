import json
import logging
import re
import sys
import time
import uuid
from collections.abc import MutableMapping
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .academic import router as academic_router
from .config import get_settings
from .external import router as external_router
from .health import router as health_router
from .internal import router as internal_router
from .knowledge import router as knowledge_router
from .metrics import metrics
from .metrics import router as metrics_router
from .pdf import router as pdf_router
from .practice import router as practice_router
from .study_plan import router as study_plan_router

REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        event: MutableMapping[str, Any] = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for field in ("method", "path", "status", "request_id"):
            if hasattr(record, field):
                event[field] = getattr(record, field)
        return json.dumps(event, ensure_ascii=False)


def configure_logging() -> None:
    settings = get_settings()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    logging.basicConfig(level=settings.log_level.upper(), handlers=[handler], force=True)


def create_app() -> FastAPI:
    configure_logging()
    application = FastAPI(
        title="Mentor Concursos API",
        version="0.1.0",
        docs_url=None,
        redoc_url=None,
    )
    application.include_router(health_router)
    application.include_router(internal_router)
    application.include_router(metrics_router)
    application.include_router(academic_router)
    application.include_router(knowledge_router)
    application.include_router(external_router)
    application.include_router(practice_router)
    application.include_router(study_plan_router)
    application.include_router(pdf_router)

    @application.exception_handler(Exception)
    async def unhandled_error(request: Request, _: Exception) -> JSONResponse:
        request_id = getattr(request.state, "request_id", "unknown")
        logging.getLogger("mentor.http").error(
            "unhandled_exception",
            extra={"request_id": request_id},
        )
        return JSONResponse(
            status_code=500,
            content={"detail": "Erro interno", "request_id": request_id},
            headers={"X-Request-ID": request_id},
        )

    @application.middleware("http")
    async def log_request(request: Request, call_next: Any) -> Any:
        supplied_id = request.headers.get("X-Request-ID", "")
        request_id = supplied_id if REQUEST_ID_PATTERN.fullmatch(supplied_id) else str(uuid.uuid4())
        request.state.request_id = request_id
        started = time.perf_counter()
        response = await call_next(request)
        route = request.scope.get("route")
        route_path = getattr(route, "path", "unmatched")
        latency = time.perf_counter() - started
        metrics.observe_request(request.method, route_path, response.status_code, latency)
        response.headers["X-Request-ID"] = request_id
        logging.getLogger("mentor.http").info(
            "request_completed",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "request_id": request_id,
            },
        )
        return response

    return application


app = create_app()
