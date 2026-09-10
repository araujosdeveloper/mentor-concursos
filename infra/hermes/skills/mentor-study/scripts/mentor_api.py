#!/usr/bin/env python3
"""Small fixed-surface client for the internal Mentor Concursos API."""

from __future__ import annotations

import argparse
import json
import os
import sys
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


def _request(method: str, path: str, telegram_id: str, payload: dict | None = None) -> dict:
    base = os.environ.get("MENTOR_API_BASE_URL", "http://mentor-concursos-api:8080").rstrip("/")
    body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode()
    headers = {
        "Authorization": f"Bearer {_token()}",
        "X-Telegram-User-ID": telegram_id,
        "X-Request-ID": str(uuid.uuid4()),
        "Accept": "application/json",
    }
    if body is not None:
        headers["Content-Type"] = "application/json"
        fingerprint = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        key_material = f"mentor:{telegram_id}:{method}:{path}:{fingerprint}"
        headers["Idempotency-Key"] = str(uuid.uuid5(uuid.NAMESPACE_URL, key_material))
    request = urllib.request.Request(f"{base}{path}", data=body, headers=headers, method=method)
    for attempt in range(2):
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
            "pausar", "retomar", "finalizar", "cancelar",
        ],
    )
    parser.add_argument("--telegram-user-id", required=True)
    parser.add_argument("--query", default="")
    args = parser.parse_args()
    try:
        if args.action == "inicio":
            result = {
                "profile": _request("GET", "/api/v1/users/me", args.telegram_user_id),
                "current": _request("GET", "/api/v1/sessions/current", args.telegram_user_id),
            }
        elif args.action == "perfil":
            result = _request("GET", "/api/v1/users/me", args.telegram_user_id)
        elif args.action == "progresso":
            result = {
                "goals": _request("GET", "/api/v1/goals", args.telegram_user_id),
                "sessions": _request("GET", "/api/v1/sessions?limit=20", args.telegram_user_id),
            }
        elif args.action == "perguntar":
            if not args.query.strip():
                raise RuntimeError("informe uma pergunta")
            result = _request(
                "POST", "/api/v1/rag/answer", args.telegram_user_id,
                {"query": args.query, "limit": 5},
            )
        elif args.action == "estudar":
            goals = _request("GET", "/api/v1/goals", args.telegram_user_id).get("items", [])
            current = _request("GET", "/api/v1/sessions/current", args.telegram_user_id)
            result = {"goals": goals, "current": current, "needs_configuration": not goals}
        else:
            current = _request("GET", "/api/v1/sessions/current", args.telegram_user_id)
            if not current:
                result = {"state": "no_open_session"}
            else:
                paths = {
                    "pausar": "pause", "retomar": "resume",
                    "finalizar": "complete", "cancelar": "cancel",
                }
                result = _request(
                    "POST", f"/api/v1/sessions/{current['id']}/{paths[args.action]}",
                    args.telegram_user_id, {"version": current["version"]},
                )
        _print(result)
        return 0
    except (OSError, RuntimeError) as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    sys.exit(main())
