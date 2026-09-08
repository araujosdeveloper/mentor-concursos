#!/usr/bin/env bash
set -Eeuo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

required=(
  README.md AGENTS.md .gitignore .dockerignore .editorconfig .env.example pyproject.toml
  docker-compose.yml apps/api/Dockerfile apps/worker/Dockerfile apps/api/src/__init__.py
  apps/api/src/main.py apps/api/src/config.py apps/api/src/health.py apps/worker/src/__init__.py
  apps/worker/src/main.py database/migrations/001_extensions_and_schema.sql
  tests/unit/test_health.py docs/00-PLANO-MESTRE.md docs/01-ARQUITETURA.md
  docs/02-SEGURANCA.md docs/03-OPERACAO.md docs/adr/ADR-001-isolamento-hermes.md
  docs/adr/ADR-002-banco-dedicado.md .github/workflows/validate.yml
)

for path in "${required[@]}"; do
  test -f "$path" || { echo "FAIL arquivo ausente: $path" >&2; exit 1; }
done

test ! -e .env || { echo "FAIL .env real existe" >&2; exit 1; }
if git ls-files --error-unmatch .env >/dev/null 2>&1; then
  echo "FAIL .env rastreado" >&2
  exit 1
fi

python3 -m compileall -q apps tests

if python3 -c 'import pytest, fastapi, pydantic_settings' >/dev/null 2>&1; then
  python3 -m pytest
else
  echo "SKIP testes: dependências Python de desenvolvimento indisponíveis" >&2
fi

if command -v ruff >/dev/null 2>&1; then
  ruff check .
elif python3 -c 'import ruff' >/dev/null 2>&1; then
  python3 -m ruff check .
else
  echo "SKIP lint: ruff indisponível" >&2
fi

compose_env=(
  POSTGRES_DB=mentor_concursos
  POSTGRES_USER=validation_user
  POSTGRES_PASSWORD=validation-only-not-a-secret
  REDIS_PASSWORD=validation-only-not-a-secret
  HERMES_IMAGE=registry.example.invalid/hermes-agent:0.0.0@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
)
env "${compose_env[@]}" docker compose config --quiet
rendered="$(env "${compose_env[@]}" docker compose config)"

if grep -Eq '^[[:space:]]+ports:' <<<"$rendered"; then
  echo "FAIL porta do host publicada" >&2
  exit 1
fi
if grep -Eiq 'image:[[:space:]]*[^[:space:]]*:latest([[:space:]]|$)' docker-compose.yml; then
  echo "FAIL tag latest encontrada" >&2
  exit 1
fi
if grep -Eq 'network_mode:[[:space:]]*host|privileged:[[:space:]]*true' docker-compose.yml; then
  echo "FAIL configuração insegura de container" >&2
  exit 1
fi

tracked_storage="$(git ls-files storage/inbox storage/processed | grep -vE '/\.gitkeep$' || true)"
test -z "$tracked_storage" || { echo "FAIL conteúdo de storage rastreado" >&2; exit 1; }

if rg --hidden --glob '!.git/**' --glob '!.env.example' \
  '(BEGIN (RSA|OPENSSH|EC) PRIVATE KEY|gh[pousr]_[A-Za-z0-9_]{20,}|AKIA[0-9A-Z]{16})' .; then
  echo "FAIL possível segredo detectado" >&2
  exit 1
fi

git diff --check
echo "PASS validação da fundação"
