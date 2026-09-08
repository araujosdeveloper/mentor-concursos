import json
import logging
import sys
from collections.abc import MutableMapping
from typing import Any

from fastapi import FastAPI, Request

from .config import get_settings
from .health import router as health_router


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        event: MutableMapping[str, Any] = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for field in ("method", "path", "status"):
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

    @application.middleware("http")
    async def log_request(request: Request, call_next: Any) -> Any:
        response = await call_next(request)
        logging.getLogger("mentor.http").info(
            "request_completed",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
            },
        )
        return response

    return application


app = create_app()
