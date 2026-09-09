#!/usr/bin/env bash
set -Eeuo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."
test -f .env || { echo "ERRO: ambiente não preparado" >&2; exit 1; }

# O ID é lido somente do arquivo de pairing do Hermes dedicado. O valor nunca
# é impresso; a validação exige exatamente uma autorização aprovada.
telegram_user_id="$(docker exec mentor-concursos-hermes python -c '
import json
from pathlib import Path
p = json.loads(Path("/opt/data/platforms/pairing/telegram-approved.json").read_text())
ids = list(p) if isinstance(p, dict) else []
if len(ids) != 1 or not ids[0].isdigit():
    raise SystemExit("quantidade de pairings aprovada inesperada")
print(ids[0], end="")
')"
test -n "$telegram_user_id"

docker compose exec -T -e "PROVISION_TELEGRAM_USER_ID=$telegram_user_id" mentor-concursos-postgres sh -ceu 'PGPASSWORD="$POSTGRES_PASSWORD" exec psql -v ON_ERROR_STOP=1 -v telegram_user_id="$PROVISION_TELEGRAM_USER_ID" -U "$POSTGRES_USER" -d "$POSTGRES_DB"' <<'SQL'
INSERT INTO mentor_concursos.users(telegram_user_id, name, timezone, available_minutes_per_day)
VALUES (:telegram_user_id, 'Roberto Araujo', 'America/Sao_Paulo', 210)
ON CONFLICT (telegram_user_id) DO UPDATE SET
  name=EXCLUDED.name,
  timezone=EXCLUDED.timezone,
  available_minutes_per_day=EXCLUDED.available_minutes_per_day,
  status='active';
INSERT INTO mentor_concursos.audit_events(actor, action, entity, entity_id, request_id, metadata)
SELECT 'provisioning', 'user_provisioned', 'users', id, 'provision-roberto', '{}'::jsonb
FROM mentor_concursos.users WHERE telegram_user_id=:telegram_user_id
  AND NOT EXISTS (SELECT 1 FROM mentor_concursos.audit_events WHERE action='user_provisioned' AND entity_id=mentor_concursos.users.id);
SQL
echo "PASS Roberto provisionado de forma idempotente; nenhuma entidade acadêmica criada"
