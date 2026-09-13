"""Deterministic academic-command dispatcher at Hermes ingress."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import time
import unicodedata
import urllib.error
import urllib.request
import uuid
from contextlib import suppress

from mentor_consultation_memory import context_for, record

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


def _call_bytes(method, path, ctx, payload=None) -> bytes:
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
            timeout=30,
        ) as r:
            return r.read()
    except (
        urllib.error.HTTPError,
        urllib.error.URLError,
        TimeoutError,
    ) as error:
        if isinstance(error, urllib.error.HTTPError):
            detail = ""
            with suppress(Exception):
                detail = error.read().decode("utf-8", "replace")[:400]
            LOGGER.warning("mentor_api_request_failed status=%s detail=%s", error.code, detail)
        else:
            LOGGER.warning("mentor_api_request_failed class=%s", type(error).__name__)
        raise RuntimeError("operação acadêmica indisponível") from None


def _call(method, path, ctx, payload=None):
    return json.loads(_call_bytes(method, path, ctx, payload))


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
    if cmd == "responder":
        correct = bool(result.get("correct"))
        selected = str(result.get("selected_option") or "?").upper()
        expected = str(result.get("correct_option") or "?").upper()
        citation = result.get("citation") or {}
        source = citation.get("source_name") or "fonte indexada"
        locator = citation.get("locator") or "localização não informada"
        next_review = result.get("next_review_at") or "não agendada"
        status = "Acerto" if correct else "Erro"
        lines = [
            f"{status}.",
            f"Alternativa escolhida: {selected}",
            f"Alternativa correta: {expected}",
            f"Explicação: {result.get('explanation') or 'não disponível'}",
            f"Fonte: {source}",
            f"Localizador: {locator}",
            f"Próxima revisão: {next_review}",
        ]
        return "\n".join(lines)
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
                _call, "POST", "/api/v1/external/answer", ctx, {"query": args}
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
        try:
            return _format(command, result, key)
        except (TypeError, ValueError, AttributeError):
            if command == "responder":
                return "Resposta registrada, mas a apresentação falhou. Consulte /desempenho."
            raise
    except (OSError, RuntimeError, ValueError) as error:
        LOGGER.warning("academic_command_failed class=%s", type(error).__name__)
        return "Erro técnico temporário. Nenhuma operação acadêmica foi realizada."


def _lesson_markdowns(session_id: str, limit: int = 10) -> list[str]:
    """Retorna as últimas aulas (respostas substantivas), da mais recente para a mais antiga."""
    import sqlite3

    db_path = os.path.join(os.environ.get("HERMES_HOME", "/opt/data"), "state.db")
    connection = sqlite3.connect(db_path)
    try:
        rows = connection.execute(
            "SELECT content FROM messages WHERE session_id=? AND role='assistant' "
            "AND content IS NOT NULL AND length(trim(content)) > 200 "
            "ORDER BY timestamp DESC LIMIT ?",
            (session_id, limit),
        ).fetchall()
    finally:
        connection.close()
    return [r[0] for r in rows]


def _lesson_title(markdown: str) -> str:
    for line in markdown.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip()
    return "Aula"


def _slugify(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    ascii_text = "".join(c for c in normalized if not unicodedata.combining(c))
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_text).strip("-").lower()
    return slug[:80] or "aula"


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
        is_telegram = getattr(getattr(event.source, "platform", None), "value", "") == "telegram"
        if command == "salvar" and is_telegram:
            return await _handle_salvar(self, event)
        if command == "aulas" and is_telegram:
            return await _handle_aulas(self, event)
        if command in COMMANDS and is_telegram:
            return await dispatch(event, command)
        source = getattr(event, "source", None)
        is_telegram = getattr(getattr(source, "platform", None), "value", "") == "telegram"
        if is_telegram and not command:
            previous_context = context_for(source)
            if previous_context:
                event.channel_context = previous_context
            try:
                response = await original(self, event)
            except Exception:
                raise
            record(
                source,
                getattr(event, "text", ""),
                response if isinstance(response, str) else None,
            )
            return response
        return await original(self, event)

    async def _handle_salvar(self, event):
        source = event.source
        try:
            ctx = _context(source)
        except Exception:  # noqa: BLE001
            LOGGER.exception("salvar_context_failed")
            return "Não consegui validar a identidade para salvar a aula."
        try:
            session_entry = await self.async_session_store.get_or_create_session(source)
            lessons = _lesson_markdowns(session_entry.session_id)
            if not lessons:
                return "Nenhuma aula encontrada nesta sessão para salvar."
            raw_arg = (event.get_command_args() or "").strip()
            index = 1
            if raw_arg:
                try:
                    index = int(raw_arg)
                except ValueError:
                    return "Use /salvar <número> (ex.: /salvar 1 para a mais recente)."
            if index < 1 or index > len(lessons):
                return f"Há {len(lessons)} aulas disponíveis. Use /aulas para listá-las."
            markdown = lessons[index - 1]
        except Exception:  # noqa: BLE001
            LOGGER.exception("salvar_export_failed")
            return "Não consegui extrair a aula da conversa."
        try:
            title = _lesson_title(markdown)
            pdf_bytes = _call_bytes(
                "POST", "/api/v1/lessons/pdf", ctx,
                {"title": title, "content": markdown},
            )
        except Exception:  # noqa: BLE001
            LOGGER.exception("salvar_pdf_generation_failed")
            return "Não consegui gerar o PDF da aula."
        try:
            import tempfile

            pdf_path = os.path.join(tempfile.gettempdir(), f"aula_{ctx['user_id']}.pdf")
            with open(pdf_path, "wb") as f:
                f.write(pdf_bytes)
            adapter = getattr(self, "_adapter_for_source", None)
            if adapter is None:
                return "Não foi possível enviar o documento."
            adapter = adapter(source)
            await adapter.send_document(
                chat_id=source.chat_id,
                file_path=pdf_path,
                caption=title,
                file_name=f"{_slugify(title)}.pdf",
            )
            return "Aula salva em PDF e enviada."
        except Exception:  # noqa: BLE001
            LOGGER.exception("salvar_send_failed")
            return "PDF gerado, mas não consegui enviar o arquivo."

    async def _handle_aulas(self, event):
        source = event.source
        try:
            session_entry = await self.async_session_store.get_or_create_session(source)
            lessons = _lesson_markdowns(session_entry.session_id)
        except Exception:  # noqa: BLE001
            LOGGER.exception("aulas_failed")
            return "Não consegui listar as aulas."
        if not lessons:
            return "Nenhuma aula encontrada nesta sessão."
        lines = ["Aulas recentes:"]
        for i, markdown in enumerate(lessons, start=1):
            title = _lesson_title(markdown)
            lines.append(f"{i}. {title}")
        lines.append("Para salvar em PDF: /salvar <número>")
        return "\n".join(lines)

    runner._handle_message = guarded
    INSTALLED = True
