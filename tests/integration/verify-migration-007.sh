#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."

database="mentor_concursos_migration_007_$$"
case "$database" in mentor_concursos_migration_007_[0-9]*) ;; *) exit 1 ;; esac

cleanup() {
  docker exec mentor-concursos-postgres sh -ceu \
    'PGPASSWORD="$POSTGRES_PASSWORD" dropdb --if-exists -U "$POSTGRES_USER" "$1"' \
    sh "$database" >/dev/null
}
trap cleanup EXIT

docker exec mentor-concursos-postgres sh -ceu \
  'PGPASSWORD="$POSTGRES_PASSWORD" createdb -U "$POSTGRES_USER" "$1"' sh "$database"

docker exec -i mentor-concursos-postgres sh -ceu \
  'PGPASSWORD="$POSTGRES_PASSWORD" psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$1"' \
  sh "$database" <<'SQL'
CREATE SCHEMA mentor_concursos;
CREATE TABLE mentor_concursos.users (id UUID PRIMARY KEY);
INSERT INTO mentor_concursos.users(id) VALUES ('00000000-0000-0000-0000-000000000001');
SQL

docker exec -i mentor-concursos-postgres sh -ceu \
  'PGPASSWORD="$POSTGRES_PASSWORD" psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$1"' \
  sh "$database" < database/migrations/007_source_review_rbac.sql

result="$(docker exec mentor-concursos-postgres sh -ceu \
  'PGPASSWORD="$POSTGRES_PASSWORD" psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$1" -Atc "SELECT role FROM mentor_concursos.users WHERE id='"'"'00000000-0000-0000-0000-000000000001'"'"'"' \
  sh "$database")"
test "$result" = student
echo "PASS migration 007 atribui student a usuário existente"
