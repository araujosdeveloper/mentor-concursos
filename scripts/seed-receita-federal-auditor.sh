#!/usr/bin/env bash
set -Eeuo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."
test -f .env || { echo "ERRO: ambiente não preparado" >&2; exit 1; }
docker compose exec -T mentor-concursos-postgres sh -ceu '
  PGPASSWORD="$POSTGRES_PASSWORD" psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"
' < database/seeds/002_receita_federal_auditor_fiscal.sql
echo "PASS edital piloto Receita Federal (Auditor-Fiscal) aplicado de forma idempotente"
