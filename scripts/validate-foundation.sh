#!/usr/bin/env bash
set -Eeuo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

required=(
  README.md AGENTS.md .gitignore .dockerignore .editorconfig .env.example pyproject.toml
  docker-compose.yml apps/api/Dockerfile apps/worker/Dockerfile apps/api/src/__init__.py
  apps/api/src/main.py apps/api/src/config.py apps/api/src/health.py apps/worker/src/__init__.py
  apps/api/src/auth.py apps/api/src/dependencies.py apps/api/src/internal.py
  apps/api/src/metrics.py apps/api/src/rate_limit.py
  apps/api/entrypoint.sh
  apps/worker/src/main.py apps/migrations/main.py database/migrations/001_extensions_and_schema.sql
  scripts/prepare-production-env.sh scripts/apply-migrations.sh tests/unit/test_health.py
  tests/unit/test_auth.py docs/00-PLANO-MESTRE.md docs/01-ARQUITETURA.md
  docs/02-SEGURANCA.md docs/03-OPERACAO.md docs/adr/ADR-001-isolamento-hermes.md
  docs/adr/ADR-002-banco-dedicado.md docs/adr/ADR-003-imagem-hermes.md
  docs/adr/ADR-004-autenticacao-servico.md docs/04-INVENTARIO-IMAGENS.md
  docs/runbooks/DEPLOY.md docs/runbooks/BACKUP-RESTORE.md tests/integration/verify-core.sh
  infra/egress/squid.conf infra/egress/allowlist-domains.txt infra/egress/entrypoint.sh requirements.lock
  requirements-dev.lock scripts/verify-lock.sh scripts/update-locks.sh
  docs/05-OBSERVABILIDADE-E-EGRESS.md docs/adr/ADR-005-politica-egress.md
  docs/adr/ADR-006-dependencias-reproduziveis.md docs/runbooks/DIAGNOSTICO.md
  .github/workflows/validate.yml
)

for path in "${required[@]}"; do
  test -f "$path" || { echo "FAIL arquivo ausente: $path" >&2; exit 1; }
done

if git ls-files --error-unmatch .env >/dev/null 2>&1; then
  echo "FAIL .env rastreado" >&2
  exit 1
fi
if [[ -e .env && "$(stat -c '%a' .env)" != "600" ]]; then
  echo "FAIL .env deve ter permissão 600" >&2
  exit 1
fi
if [[ -e secrets ]]; then
  [[ "$(stat -c '%a' secrets)" == "700" ]] || { echo "FAIL secrets deve ser 700" >&2; exit 1; }
  while IFS= read -r secret; do
    [[ "$(stat -c '%a' "$secret")" == "600" ]] || { echo "FAIL secret deve ser 600" >&2; exit 1; }
  done < <(find secrets -maxdepth 1 -type f)
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
grep -Eq 'mentor-concursos-egress-proxy:' docker-compose.yml
grep -Eq 'mentor-concursos-egress-internal:' docker-compose.yml
grep -Eq 'mentor-concursos-egress-uplink:' docker-compose.yml
grep -Eq 'max-size:[[:space:]]*10m' docker-compose.yml
grep -Eq 'max-file:[[:space:]]*"3"' docker-compose.yml
grep -Eq 'ubuntu/squid:[^[:space:]]+@sha256:[0-9a-f]{64}' docker-compose.yml
grep -Eq 'api\.telegram\.org' infra/egress/allowlist-domains.txt
grep -Eq '^\.chatgpt\.com$' infra/egress/allowlist-domains.txt
grep -Eq '^auth\.openai\.com$' infra/egress/allowlist-domains.txt
if grep -Eq '^[[:space:]]*http_access[[:space:]]+allow[[:space:]]+all([[:space:]]|$)' infra/egress/squid.conf; then
  echo "FAIL proxy com liberação irrestrita" >&2
  exit 1
fi
./scripts/verify-lock.sh
grep -Eq 'mentor-concursos-hermes:' docker-compose.yml
grep -Eq 'profiles:[[:space:]]*\[mentor-concursos-hermes\]' docker-compose.yml
if grep -Eq '^    image: .*:latest([@[:space:]]|$)' docker-compose.yml; then
  echo "FAIL tag latest encontrada" >&2
  exit 1
fi

tracked_storage="$(git ls-files storage/inbox storage/processed | grep -vE '/\.gitkeep$' || true)"
test -z "$tracked_storage" || { echo "FAIL conteúdo de storage rastreado" >&2; exit 1; }

if rg --hidden --glob '!.git/**' --glob '!.env' --glob '!secrets/**' --glob '!.env.example' \
  '(BEGIN (RSA|OPENSSH|EC) PRIVATE KEY|gh[pousr]_[A-Za-z0-9_]{20,}|AKIA[0-9A-Z]{16})' .; then
  echo "FAIL possível segredo detectado" >&2
  exit 1
fi

git diff --check
echo "PASS validação da fundação"
