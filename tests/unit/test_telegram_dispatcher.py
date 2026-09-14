from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _module():
    path = Path(__file__).parents[2] / "infra" / "hermes" / "mentor_telegram_dispatcher.py"
    sys.path.insert(0, str(path.parent))
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


def test_question_idempotency_key_changes_per_telegram_update(monkeypatch) -> None:
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

    monkeypatch.setattr(dispatcher, "_secret", lambda _path: "test-secret")
    monkeypatch.setattr(dispatcher.urllib.request, "urlopen", fake_urlopen)
    base = {"user_id": "1", "chat_id": "1", "request_id": "m1"}
    dispatcher._call("POST", "/api/v1/practice/question", base, {})
    dispatcher._call("POST", "/api/v1/practice/question", {**base, "request_id": "m2"}, {})
    assert captured[0] != captured[1]


def test_answer_formats_real_api_contract_without_internal_identifiers() -> None:
    dispatcher = _module()
    rendered = dispatcher._format(
        "responder",
        {
            "question_id": "12454f2c-c75c-42aa-9bac-c391a0bdce29",
            "correct": True,
            "selected_option": "A",
            "correct_option": "A",
            "explanation": "A alternativa correta reproduz o trecho indexado indicado na citação.",
            "citation": {
                "hash": "3224ae7883b57ad829eff2107f8df32852d486734c9999683d88a9afb49e2ed4",
                "locator": "Art. 68.",
                "chunk_id": "41c42172-bcde-4989-9766-fa0a9adb16a6",
                "source_name": "Lei nº 9.784/1999 — Processo Administrativo Federal",
                "official_url": "https://www2.camara.leg.br/legin/fed/lei/1999/lei-9784-29-janeiro-1999-322239-norma-pl.html",
                "source_version_id": "1eccd249-b219-4d96-8e36-5dba1535159e",
            },
            "next_review_at": "2026-09-14T15:27:22.943733+00:00",
        },
        ("user", "chat"),
    )
    assert "Acerto." in rendered
    assert "Alternativa escolhida: A" in rendered
    assert "Alternativa correta: A" in rendered
    assert "Art. 68." in rendered
    assert "12454f2c" not in rendered
    assert "3224ae78" not in rendered


def test_answer_retry_uses_same_idempotent_request_and_formats_again(monkeypatch) -> None:
    dispatcher = _module()
    dispatcher.CURRENT[("1", "1")] = "question-id"
    calls = []

    def fake_call(method, path, ctx, payload=None):
        calls.append((method, path, payload))
        return {
            "correct": True,
            "selected_option": "A",
            "correct_option": "A",
            "explanation": "ok",
            "citation": {"source_name": "Fonte", "locator": "Art. 1."},
            "next_review_at": "amanhã",
        }

    monkeypatch.setattr(dispatcher, "_call", fake_call)

    async def immediate_to_thread(function, *args, **kwargs):
        return function(*args, **kwargs)

    monkeypatch.setattr(dispatcher.asyncio, "to_thread", immediate_to_thread)

    class Event:
        source = type(
            "Source",
            (),
            {
                "platform": type("Platform", (), {"value": "telegram"}),
                "user_id": "1",
                "chat_id": "1",
                "message_id": "answer-retry",
            },
        )()

        def get_command_args(self):
            return "A"

    import asyncio

    first = asyncio.run(dispatcher.dispatch(Event(), "responder"))
    dispatcher.CURRENT[("1", "1")] = "question-id"
    second = asyncio.run(dispatcher.dispatch(Event(), "responder"))
    assert first == second
    assert len(calls) == 2


def test_plan_today_is_short_and_hides_internal_ids() -> None:
    dispatcher = _module()
    rendered = dispatcher._format_plan_view(
        "hoje",
        {
            "date": "2026-09-14",
            "capacity_minutes": 150,
            "planned_minutes": 60,
            "items": [
                {
                    "id": "secret-uuid",
                    "subject_name": "Português",
                    "topic_name": "Crase",
                    "activity_type": "study",
                    "planned_minutes": 60,
                    "status": "planned",
                }
            ],
        },
    )
    assert "Português — Crase" in rendered
    assert "secret-uuid" not in rendered


def test_plan_confirmation_rejects_ambiguity_then_confirms(monkeypatch) -> None:
    import asyncio

    dispatcher = _module()
    calls = []

    def fake_call(method, path, _ctx, payload=None):
        calls.append((method, path, payload))
        return {"plan_items": 12}

    monkeypatch.setattr(dispatcher, "_call", fake_call)

    async def immediate(function, *args, **kwargs):
        return function(*args, **kwargs)

    monkeypatch.setattr(dispatcher.asyncio, "to_thread", immediate)
    key = ("1", "1")
    dispatcher.PLAN_FLOWS[key] = {
        "stage": "confirmation",
        "proposal_id": "internal",
        "updated_at": dispatcher.time.time(),
    }

    class Event:
        text = "talvez"

    ctx = {"user_id": "1", "chat_id": "1", "request_id": "m1"}
    assert "Ainda não confirmei" in asyncio.run(dispatcher._plan_reply(Event(), ctx, key))
    assert calls == []
    Event.text = "Confirmo"
    assert "Plano criado" in asyncio.run(dispatcher._plan_reply(Event(), ctx, key))
    assert calls[0][1].endswith("/confirm")


def test_plan_command_resumes_persisted_proposal_after_restart(monkeypatch) -> None:
    import asyncio

    dispatcher = _module()

    def fake_call(_method, path, _ctx, _payload=None):
        assert path.endswith("/proposals/current")
        return {
            "state": "pending",
            "proposal": {
                "id": "internal",
                "calculated_summary": {
                    "period": {"calendar_days": 30, "available_days": 25},
                    "total_capacity_minutes": 3000,
                    "blocks": 50,
                },
            },
        }

    monkeypatch.setattr(dispatcher, "_call", fake_call)

    async def immediate(function, *args, **kwargs):
        return function(*args, **kwargs)

    monkeypatch.setattr(dispatcher.asyncio, "to_thread", immediate)
    key = ("1", "1")
    result = asyncio.run(dispatcher._plan_command(None, {"user_id": "1", "chat_id": "1"}, key, ""))
    assert "Proposta de 30 dias" in result
    assert dispatcher.PLAN_FLOWS[key]["stage"] == "confirmation"
