#!/usr/bin/env bash
set -Eeuo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."
test -f .env || { echo "ERRO: ambiente não preparado" >&2; exit 1; }
docker compose exec -T mentor-concursos-postgres sh -ceu '
  PGPASSWORD="$POSTGRES_PASSWORD" psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"
' < database/seeds/001_reference_taxonomy.sql
echo "PASS taxonomia referencial aplicada de forma idempotente"
