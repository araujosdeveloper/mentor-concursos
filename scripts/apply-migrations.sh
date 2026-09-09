#!/usr/bin/env bash
set -Eeuo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."
test -f .env || { echo "ERRO: execute scripts/prepare-production-env.sh" >&2; exit 1; }
docker compose --profile tools run --rm mentor-concursos-migrate
