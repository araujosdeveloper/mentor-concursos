#!/usr/bin/env python3
"""Small fixed-surface client for the internal Mentor Concursos API."""

# ruff: noqa: E501

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import secrets
import sys
import time
import urllib.error
import urllib.request
import uuid


def _token() -> str:
    path = os.environ.get("MENTOR_API_SERVICE_TOKEN_FILE", "/run/mentor_api_service_token")
    with open(path, encoding="utf-8") as secret_file:
        value = secret_file.read().strip()
    if not value:
        raise RuntimeError("token ausente")
    return value


def _trusted_context() -> dict[str, str]:
    """Read only gateway-bound session context, never message arguments."""
    context = {
        "platform": os.environ.get("HERMES_SESSION_PLATFORM", "").strip().lower(),
        "user_id": os.environ.get("HERMES_SESSION_USER_ID", "").strip(),
        "chat_id": os.environ.get("HERMES_SESSION_CHAT_ID", "").strip(),
        "request_id": os.environ.get("HERMES_SESSION_MESSAGE_ID", "").strip(),
    }
    if context["platform"] != "telegram" or not all(
        context[key] for key in ("user_id", "chat_id", "request_id")
    ):
        raise RuntimeError("contexto Telegram confiável ausente")
    if not context["user_id"].lstrip("-").isdigit() or not context["chat_id"].lstrip("-").isdigit():
        raise RuntimeError("contexto Telegram inválido")
    return context


def _request(method: str, path: str, context: dict[str, str], payload: dict | None = None) -> dict:
    base = os.environ.get("MENTOR_API_BASE_URL", "http://mentor-concursos-api:8080").rstrip("/")
    body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode()
    service_token = _token()
    if body is not None:
        fingerprint = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        key_material = f"mentor:{context['user_id']}:{method}:{path}:{fingerprint}"
        idempotency_key = str(uuid.uuid5(uuid.NAMESPACE_URL, key_material))
    for attempt in range(2):
        key_path = os.environ.get("MENTOR_CONTEXT_HMAC_KEY_FILE", "/run/secrets/hermes_context_hmac_key")
        try:
            with open(key_path, "rb") as key_file:
                hmac_key = key_file.read().strip()
        except OSError:
            raise RuntimeError("contexto assinado indisponível") from None
        if not hmac_key:
            raise RuntimeError("contexto assinado indisponível")
        timestamp = int(time.time())
        nonce = secrets.token_hex(16)
        canonical = f"{context['user_id']}.{context['chat_id']}.{timestamp}.{nonce}"
        signed_context = json.dumps(
            {
                "telegram_user_id": int(context["user_id"]),
                "chat_id": int(context["chat_id"]),
                "ts": timestamp,
                "nonce": nonce,
            },
            separators=(",", ":"),
        )
        headers = {
            "Authorization": f"Bearer {service_token}",
            "X-Telegram-User-ID": context["user_id"],
            "X-Telegram-Chat-ID": context["chat_id"],
            "X-Mentor-Channel": context["platform"],
            "X-Request-ID": context["request_id"],
            "X-Hermes-Context": signed_context,
            "X-Hermes-Signature": hmac.new(hmac_key, canonical.encode(), hashlib.sha256).hexdigest(),
            "Accept": "application/json",
        }
        if body is not None:
            headers["Content-Type"] = "application/json"
            headers["Idempotency-Key"] = idempotency_key
        request = urllib.request.Request(f"{base}{path}", data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=12) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as error:
            if error.code in {401, 403, 404}:
                raise RuntimeError("operação não autorizada ou não encontrada") from None
            if error.code == 409:
                raise RuntimeError("operação em conflito; tente novamente") from None
            if attempt == 1:
                raise RuntimeError("API indisponível") from None
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            if attempt == 1:
                raise RuntimeError("API indisponível") from None


def _print(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, separators=(",", ":")))


def main() -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument(
        "action",
        choices=[
        "inicio", "perfil", "progresso", "perguntar", "estudar",
            "pausar", "retomar", "finalizar", "cancelar", "questao",
            "responder", "simulado", "revisar", "erros", "desempenho",
            "concursos", "plano",
        ],
    )
    parser.add_argument("--query", default="")
    parser.add_argument("--option", default="")
    parser.add_argument("--question-id", default="")
    parser.add_argument("--quantity", default="5")
    parser.add_argument("--exam-id", default="")
    parser.add_argument("--deadline", default="")
    parser.add_argument("--days-per-week", default="")
    parser.add_argument("--hours-per-day", default="")
    args = parser.parse_args()
    try:
        context = _trusted_context()
        if args.action == "inicio":
            result = {
                "profile": _request("GET", "/api/v1/users/me", context),
                "current": _request("GET", "/api/v1/sessions/current", context),
            }
        elif args.action == "perfil":
            result = _request("GET", "/api/v1/users/me", context)
        elif args.action == "progresso":
            result = {
                "goals": _request("GET", "/api/v1/goals", context),
                "sessions": _request("GET", "/api/v1/sessions?limit=20", context),
            }
        elif args.action == "perguntar":
            if not args.query.strip():
                raise RuntimeError("informe uma pergunta")
            result = _request(
                "POST", "/api/v1/external/answer", context,
                {"query": args.query},
            )
        elif args.action == "estudar":
            goals = _request("GET", "/api/v1/goals", context).get("items", [])
            current = _request("GET", "/api/v1/sessions/current", context)
            result = {"goals": goals, "current": current, "needs_configuration": not goals}
        elif args.action == "questao":
            result = _request("POST", "/api/v1/practice/question", context, {})
        elif args.action == "responder":
            if not args.question_id or not args.option:
                raise RuntimeError("informe a questão e a alternativa")
            result = _request("POST", "/api/v1/practice/answer", context,
                              {"question_id": args.question_id, "option": args.option})
        elif args.action == "simulado":
            try:
                quantity = int(args.quantity)
            except ValueError:
                raise RuntimeError("quantidade inválida") from None
            result = _request("POST", "/api/v1/practice/simulation", context, {"quantity": quantity})
        elif args.action == "revisar":
            result = _request("GET", "/api/v1/practice/reviews/next", context)
        elif args.action == "erros":
            result = _request("GET", "/api/v1/practice/errors", context)
        elif args.action == "desempenho":
            result = _request("GET", "/api/v1/practice/performance", context)
        elif args.action == "concursos":
            result = _request("GET", "/api/v1/exams", context)
        elif args.action == "plano":
            if not all([args.exam_id, args.deadline, args.days_per_week, args.hours_per_day]):
                raise RuntimeError("informe concurso, prazo, dias por semana e horas por dia")
            result = _request("POST", "/api/v1/study/plan", context,
                              {"exam_id": args.exam_id, "deadline": args.deadline,
                               "days_per_week": int(args.days_per_week),
                               "hours_per_day": int(args.hours_per_day)})
        elif args.action == "cancelar":
            result = _request("POST", "/api/v1/practice/cancel", context, {"cancel": True})
            if result.get("state") == "nothing_to_cancel":
                current = _request("GET", "/api/v1/sessions/current", context)
                if current:
                    result = _request("POST", f"/api/v1/sessions/{current['id']}/cancel", context, {"version": current["version"]})
        else:
            current = _request("GET", "/api/v1/sessions/current", context)
            if not current:
                result = {"state": "no_open_session"}
            else:
                paths = {
                    "pausar": "pause", "retomar": "resume", "finalizar": "complete",
                }
                result = _request(
                    "POST", f"/api/v1/sessions/{current['id']}/{paths[args.action]}",
                    context, {"version": current["version"]},
                )
        _print(result)
        return 0
    except (OSError, RuntimeError) as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    sys.exit(main())
