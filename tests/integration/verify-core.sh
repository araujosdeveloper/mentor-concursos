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


def request(path: str, token: str | None = None, request_id: str | None = None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    if request_id:
        headers["X-Request-ID"] = request_id
    req = urllib.request.Request(f"http://127.0.0.1:8080{path}", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            return response.status, response.headers, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.headers, error.read()


assert request("/api/health/live")[0] == 200
status, headers, _ = request("/api/health/ready", request_id="integration-1-2")
assert status == 200 and headers["X-Request-ID"] == "integration-1-2"
assert request("/api/internal/auth-check")[0] == 401
with open("/run/secrets/mentor_api_service_token", encoding="utf-8") as token_file:
    token = token_file.read().strip()
status, _, payload = request("/api/internal/auth-check", token)
assert status == 200 and json.loads(payload)["status"] == "ok"
status, _, payload = request("/api/internal/metrics", token)
assert status == 200 and b"mentor_api_requests_total" in payload

limited = False
for _ in range(61):
    status, headers, payload = request("/api/internal/auth-check", token)
    if status == 429:
        assert headers["Retry-After"] == "60"
        assert json.loads(payload)["detail"] == "Limite de requisições excedido"
        limited = True
        break
assert limited
print("API, readiness, request ID, autenticação, métricas e rate limit validados sem exibir o token.")
PY

docker compose exec -T mentor-concursos-worker python -m apps.worker.src.main --healthcheck
echo "PASS integração do núcleo"
