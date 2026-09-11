from __future__ import annotations

import importlib.util
from pathlib import Path


def _module():
    path = Path(__file__).parents[2] / "infra" / "hermes" / "mentor_telegram_dispatcher.py"
    spec = importlib.util.spec_from_file_location("mentor_telegram_dispatcher_test", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_question_serializes_api_option_as_letter() -> None:
    dispatcher = _module()
    rendered = dispatcher._format(
        "questao",
        {
            "prompt": "Enunciado sintético",
            "alternatives": [
                {"option": "A", "text": "Primeira"},
                {"option": "B", "text": "Segunda"},
            ],
        },
        ("user", "chat"),
    )
    assert "A) Primeira" in rendered
    assert "B) Segunda" in rendered
    assert "?)" not in rendered


def test_gateway_literal_slash_command_is_normalized() -> None:
    import asyncio

    dispatcher = _module()

    class Runner:
        async def _handle_message(self, _event):
            return "fallback"

    class Event:
        source = type("Source", (), {"platform": type("Platform", (), {"value": "telegram"})})()

        def get_command(self):
            return "/questao"

    seen = []

    async def fake_dispatch(_event, command):
        seen.append(command)
        return "handled"

    dispatcher.dispatch = fake_dispatch
    dispatcher.install(type("Gateway", (), {"GatewayRunner": Runner}))
    # The installed wrapper must recognize the raw Telegram spelling instead
    # of delegating to the generic skill/model path.
    assert Runner._handle_message.__module__ == dispatcher.__name__
    assert asyncio.run(Runner()._handle_message(Event())) == "handled"
    assert seen == ["questao"]


def test_question_idempotency_key_changes_per_telegram_update() -> None:
    dispatcher = _module()
    captured = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b'{"id":"question"}'

    def fake_urlopen(request, timeout):
        captured.append(request.headers["Idempotency-key"])
        return Response()

    dispatcher._secret = lambda _path: "test-secret"
    dispatcher.urllib.request.urlopen = fake_urlopen
    base = {"user_id": "1", "chat_id": "1", "request_id": "m1"}
    dispatcher._call("POST", "/api/v1/practice/question", base, {})
    dispatcher._call("POST", "/api/v1/practice/question", {**base, "request_id": "m2"}, {})
    assert captured[0] != captured[1]
