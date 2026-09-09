import asyncio

import httpx

from apps.api.src.main import REQUEST_ID_PATTERN, create_app


def test_request_id_accepts_bounded_safe_value() -> None:
    assert REQUEST_ID_PATTERN.fullmatch("fase-1_2-request")


def test_request_id_rejects_unbounded_or_unsafe_value() -> None:
    assert REQUEST_ID_PATTERN.fullmatch("x" * 65) is None
    assert REQUEST_ID_PATTERN.fullmatch("token?value=secret") is None


def test_request_id_is_propagated() -> None:
    async def call() -> httpx.Response:
        transport = httpx.ASGITransport(app=create_app())
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.get(
                "/api/health/live", headers={"X-Request-ID": "request-safe-1"}
            )

    response = asyncio.run(call())
    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "request-safe-1"


def test_unhandled_error_is_uniform_without_traceback() -> None:
    application = create_app()

    @application.get("/test/internal-error")
    async def fail_for_test() -> None:
        raise RuntimeError("detalhe sensível que não deve chegar ao cliente")

    async def call() -> httpx.Response:
        transport = httpx.ASGITransport(app=application, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.get(
                "/test/internal-error", headers={"X-Request-ID": "error-safe-1"}
            )

    response = asyncio.run(call())
    assert response.status_code == 500
    assert response.json() == {"detail": "Erro interno", "request_id": "error-safe-1"}
    assert response.headers["X-Request-ID"] == "error-safe-1"
    assert "sensível" not in response.text
