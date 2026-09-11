"""Deterministic academic-command dispatcher at Hermes ingress."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import os
import secrets
import time
import urllib.error
import urllib.request
import uuid

COMMANDS = {
    "inicio",
    "ajuda",
    "perguntar",
    "perfil",
    "progresso",
    "estudar",
    "pausar",
    "retomar",
    "finalizar",
    "cancelar",
    "questao",
    "responder",
    "simulado",
    "revisar",
    "erros",
    "desempenho",
}
CURRENT = {}
INSTALLED = False
LOGGER = logging.getLogger("mentor.telegram_dispatcher")


def _secret(path):
    with open(path, encoding="utf-8") as f:
        v = f.read().strip()
    if not v:
        raise RuntimeError("credencial interna indisponível")
    return v


def _context(source):
    p = getattr(getattr(source, "platform", None), "value", "")
    u = str(getattr(source, "user_id", "") or "").strip()
    c = str(getattr(source, "chat_id", "") or "").strip()
    m = str(getattr(source, "message_id", "") or "").strip()
    if p != "telegram" or not u or not c or not m:
        raise RuntimeError("contexto Telegram confiável ausente")
    if not u.lstrip("-").isdigit() or not c.lstrip("-").isdigit():
        raise RuntimeError("contexto Telegram inválido")
    return {"user_id": u, "chat_id": c, "request_id": m}


def _call(method, path, ctx, payload=None):
    token = _secret(
        os.environ.get("MENTOR_API_SERVICE_TOKEN_FILE", "/run/mentor_api_service_token")
    )
    key = _secret(
        os.environ.get("MENTOR_CONTEXT_HMAC_KEY_FILE", "/run/secrets/hermes_context_hmac_key")
    )
    nonce = secrets.token_hex(16)
    ts = int(time.time())
    canonical = f"{ctx['user_id']}.{ctx['chat_id']}.{ts}.{nonce}"
    body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode()
    envelope = json.dumps(
        {
            "telegram_user_id": int(ctx["user_id"]),
            "chat_id": int(ctx["chat_id"]),
            "ts": ts,
            "nonce": nonce,
        },
        separators=(",", ":"),
    )
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Telegram-User-ID": ctx["user_id"],
        "X-Telegram-Chat-ID": ctx["chat_id"],
        "X-Mentor-Channel": "telegram",
        "X-Request-ID": ctx["request_id"],
        "X-Hermes-Context": envelope,
        "X-Hermes-Signature": hmac.new(
            key.encode(), canonical.encode(), hashlib.sha256
        ).hexdigest(),
        "Accept": "application/json",
    }
    if body is not None:
        headers.update(
            {
                "Content-Type": "application/json",
                "Idempotency-Key": str(
                    uuid.uuid5(
                        uuid.NAMESPACE_URL,
                        f"mentor:{ctx['user_id']}:{ctx['request_id']}:{method}:{path}:{body.decode()}",
                    )
                ),
            }
        )
    try:
        with urllib.request.urlopen(
            urllib.request.Request(
                os.environ.get("MENTOR_API_BASE_URL", "http://mentor-concursos-api:8080").rstrip(
                    "/"
                )
                + path,
                data=body,
                headers=headers,
                method=method,
            ),
            timeout=12,
        ) as r:
            return json.loads(r.read())
    except (
        urllib.error.HTTPError,
        urllib.error.URLError,
        TimeoutError,
        json.JSONDecodeError,
    ) as error:
        if isinstance(error, urllib.error.HTTPError):
            LOGGER.warning("mentor_api_request_failed status=%s", error.code)
        else:
            LOGGER.warning("mentor_api_request_failed class=%s", type(error).__name__)
        raise RuntimeError("operação acadêmica indisponível") from None


def _format(cmd, result, key):
    if cmd == "questao":
        if result.get("id"):
            CURRENT[key] = str(result["id"])
        lines = ["Questão:", str(result.get("prompt") or result.get("statement") or "")]
        for a in result.get("alternatives", []):
            # The practice API serializes the stable answer key as ``option``.
            # Keep compatibility with older payloads while never displaying a
            # placeholder when the canonical field is present.
            letter = a.get("option", a.get("letter", a.get("label", "?")))
            lines.append(
                f"{letter}) {a.get('text', '')}"
                if isinstance(a, dict)
                else str(a)
            )
        return "\n".join(lines + ["", "Responda com /responder <letra>."])
    if cmd == "ajuda":
        return "Comandos: /questao, /responder, /simulado, /revisar, /erros e /desempenho."
    return json.dumps(result, ensure_ascii=False, separators=(",", ":"))


async def dispatch(event, command):
    if command not in COMMANDS:
        return None
    try:
        ctx = _context(event.source)
        key = (ctx["user_id"], ctx["chat_id"])
        args = (event.get_command_args() or "").strip()
        if command == "ajuda":
            return _format(command, {}, key)
        if command == "questao":
            result = await asyncio.to_thread(_call, "POST", "/api/v1/practice/question", ctx, {})
        elif command == "perguntar":
            if not args:
                raise RuntimeError("informe uma pergunta")
            result = await asyncio.to_thread(
                _call, "POST", "/api/v1/rag/answer", ctx, {"query": args, "limit": 5}
            )
        elif command == "responder":
            qid = CURRENT.get(key)
            opt = args.split()[0].upper() if args else ""
            if not qid or not opt:
                raise RuntimeError("nenhuma questão aguardando resposta")
            result = await asyncio.to_thread(
                _call, "POST", "/api/v1/practice/answer", ctx, {"question_id": qid, "option": opt}
            )
            CURRENT.pop(key, None)
        elif command == "simulado":
            result = await asyncio.to_thread(
                _call, "POST", "/api/v1/practice/simulation", ctx, {"quantity": int(args or "5")}
            )
        elif command in {
            "perfil",
            "progresso",
            "estudar",
            "revisar",
            "erros",
            "desempenho",
            "inicio",
        }:
            paths = {
                "perfil": "/api/v1/users/me",
                "progresso": "/api/v1/sessions?limit=20",
                "estudar": "/api/v1/sessions/current",
                "revisar": "/api/v1/practice/reviews/next",
                "erros": "/api/v1/practice/errors",
                "desempenho": "/api/v1/practice/performance",
                "inicio": "/api/v1/users/me",
            }
            result = await asyncio.to_thread(_call, "GET", paths[command], ctx)
        elif command == "cancelar":
            result = await asyncio.to_thread(
                _call, "POST", "/api/v1/practice/cancel", ctx, {"cancel": True}
            )
        else:
            current = await asyncio.to_thread(_call, "GET", "/api/v1/sessions/current", ctx)
            if not current:
                result = {"state": "no_open_session"}
            else:
                action = {"pausar": "pause", "retomar": "resume", "finalizar": "complete"}[command]
                result = await asyncio.to_thread(
                    _call,
                    "POST",
                    f"/api/v1/sessions/{current['id']}/{action}",
                    ctx,
                    {"version": current["version"]},
                )
        return _format(command, result, key)
    except (OSError, RuntimeError, ValueError) as error:
        LOGGER.warning("academic_command_failed class=%s", type(error).__name__)
        return "Erro técnico temporário. Nenhuma operação acadêmica foi realizada."


def install(module):
    global INSTALLED
    runner = getattr(module, "GatewayRunner", None)
    original = getattr(runner, "_handle_message", None) if runner else None
    if INSTALLED or runner is None or original is None:
        return

    async def guarded(self, event):
        # Hermes may expose the raw Telegram command with its leading slash.
        # Normalize only the command token; arguments remain untouched.
        command = (event.get_command() or "").lstrip("/").lower()
        if (
            command in COMMANDS
            and getattr(getattr(event.source, "platform", None), "value", "") == "telegram"
        ):
            return await dispatch(event, command)
        return await original(self, event)

    runner._handle_message = guarded
    INSTALLED = True
