#!/usr/bin/env bash
set -Eeuo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/../.."

docker compose exec -T mentor-concursos-postgres sh -ceu '
  PGPASSWORD="$POSTGRES_PASSWORD" psql -v ON_ERROR_STOP=1 \
    -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc \
    "SELECT extname FROM pg_extension WHERE extname = '\''vector'\'';
     SELECT schema_name FROM information_schema.schemata WHERE schema_name = '\''mentor_concursos'\'';
     SELECT version FROM mentor_concursos.schema_migrations ORDER BY version;"
'

docker compose exec -T mentor-concursos-redis sh -ceu '
  test "$(redis-cli -a "$REDIS_PASSWORD" --no-auth-warning ping)" = PONG
'

docker compose exec -T mentor-concursos-tika wget -q -O - http://127.0.0.1:9998/version
echo

docker compose exec -T mentor-concursos-api python - <<'PY'
import json
import urllib.error
import urllib.request


def request(path: str, token: str | None = None) -> tuple[int, dict[str, object]]:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    req = urllib.request.Request(f"http://127.0.0.1:8080{path}", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as error:
        return error.code, json.load(error)


assert request("/api/health/live")[0] == 200
assert request("/api/health/ready")[0] == 200
assert request("/api/internal/auth-check")[0] == 401
with open("/run/secrets/mentor_api_service_token", encoding="utf-8") as token_file:
    token = token_file.read().strip()
status, body = request("/api/internal/auth-check", token)
assert status == 200 and body["status"] == "ok"
print("API, readiness e autenticação validados sem exibir o token.")
PY

docker compose exec -T mentor-concursos-worker python -m apps.worker.src.main --healthcheck
echo "PASS integração do núcleo"
