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
  Dockerfile.validation
  database/migrations/002_academic_core.sql database/migrations/003_topic_cycle_guard.sql database/seeds/001_reference_taxonomy.sql
  database/migrations/004_knowledge_pipeline.sql apps/worker/src/knowledge.py apps/worker/src/embedding_service.py apps/worker/src/pipeline.py
  database/migrations/006_official_source_refresh.sql apps/worker/src/source_refresh.py
  database/migrations/007_source_review_rbac.sql apps/api/src/knowledge_review.py
  docs/adr/ADR-019-consolidacao-refresh-seguro.md scripts/set-user-role.py
  tests/unit/test_source_review.py tests/unit/test_worker_consumer.py
  tests/unit/test_set_user_role.py tests/integration/verify-migration-007.sh
  database/migrations/005_practice_review.sql apps/api/src/practice.py
  apps/api/src/knowledge.py apps/embeddings/Dockerfile apps/embeddings/requirements-real.lock apps/embeddings/model-cpu.manifest.sha256 Dockerfile.validation.dockerignore docs/AUTONOMIA-OPERACIONAL.md
  docs/runbooks/EMBEDDINGS.md docs/adr/ADR-016-runtime-cpu-onnx.md
  scripts/benchmark-knowledge.py
  apps/api/src/academic.py scripts/seed-reference-taxonomy.sh scripts/provision-roberto.sh
  tests/unit/test_academic.py
  tests/integration/verify-academic-db.sh
  tests/integration/verify-knowledge-db.sh tests/unit/test_knowledge.py tests/unit/test_practice.py
  tests/integration/verify-telegram-routing.sh
  docs/06-MODELO-ACADEMICO.md docs/07-API-ACADEMICA.md
  docs/adr/ADR-010-nucleo-academico.md docs/adr/ADR-011-calculo-tempo-liquido.md
  docs/adr/ADR-012-idempotencia-academica.md docs/runbooks/MIGRATIONS-ACADEMIC.md
  docs/11-FONTES-OFICIAIS-E-ATUALIZACAO.md scripts/refresh-official-source.py
  tests/unit/test_source_refresh.py config/official-sources.yaml
  docs/adr/ADR-020-consulta-externa-fontes-oficiais.md
  apps/external/__init__.py apps/external/catalog.py
  apps/external/cache.py apps/external/service.py apps/external/Dockerfile
  apps/external/fetch.py
  apps/external/connectors/__init__.py apps/external/connectors/legislation.py
  apps/external/connectors/jurisprudence.py
  apps/external/ssl/gsgccr6alphasslca2025.crt
  apps/api/src/external.py
  tests/unit/test_source_catalog.py tests/unit/test_external_cache.py
  tests/unit/test_external_service.py tests/unit/test_external_api.py
  tests/unit/test_fetch.py tests/unit/test_legislation.py
  tests/unit/test_jurisprudence.py
)

for path in "${required[@]}"; do
  test -f "$path" || { echo "FAIL arquivo ausente: $path" >&2; exit 1; }
done

if command -v git >/dev/null 2>&1 && git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  if git ls-files --error-unmatch .env >/dev/null 2>&1; then
    echo "FAIL .env rastreado" >&2
    exit 1
  fi
else
  echo "INFO git indisponível; verificação de rastreamento será feita pela CI" >&2
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
if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
  env "${compose_env[@]}" docker compose config --quiet
  rendered="$(env "${compose_env[@]}" docker compose config)"
else
  [[ "${FOUNDATION_COMPOSE_PREVALIDATED:-0}" == "1" ]] || {
    echo "FAIL docker compose indisponível" >&2
    exit 1
  }
  echo "INFO docker compose ausente; configuração validada externamente" >&2
  rendered="$(cat docker-compose.yml)"
fi

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
if grep -Eiq '(^|[-_])(cuda|cudnn|cublas|nccl|triton|nvidia)([-_]|$)' apps/embeddings/requirements-real.lock; then
  echo "FAIL dependência CUDA no runtime de embeddings" >&2
  exit 1
fi
grep -Eq 'api\.telegram\.org' infra/egress/allowlist-domains.txt
grep -Eq '^\.chatgpt\.com$' infra/egress/allowlist-domains.txt
grep -Eq '^auth\.openai\.com$' infra/egress/allowlist-domains.txt
grep -Eq '^www\.planalto\.gov\.br$' infra/egress/allowlist-domains.txt
grep -Eq '^jurisprudencias\.ai$' infra/egress/allowlist-domains.txt
grep -Eq 'mentor-concursos-external:' docker-compose.yml
grep -Eq 'mentor-concursos-egress-internal' docker-compose.yml
grep -Eq 'jurisprudencias_api_token' docker-compose.yml
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

if command -v git >/dev/null 2>&1 && git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  tracked_storage="$(git ls-files storage/inbox storage/processed | grep -vE '/\.gitkeep$' || true)"
else
  tracked_storage="$(find storage/inbox storage/processed -type f ! -name .gitkeep -print 2>/dev/null || true)"
fi
test -z "$tracked_storage" || { echo "FAIL conteúdo de storage rastreado" >&2; exit 1; }

secret_pattern='(BEGIN (RSA|OPENSSH|EC) PRIVATE KEY|gh[pousr]_[A-Za-z0-9_]{20,}|AKIA[0-9A-Z]{16})'
if command -v rg >/dev/null 2>&1; then
  secret_scan=(rg --hidden --glob '!.git/**' --glob '!.env' --glob '!secrets/**' --glob '!.env.example' "$secret_pattern" .)
else
  secret_scan=(grep -RInE --exclude-dir=.git --exclude=.env --exclude=.env.example --exclude-dir=secrets "$secret_pattern" .)
fi
if "${secret_scan[@]}"; then
  echo "FAIL possível segredo detectado" >&2
  exit 1
fi

if command -v git >/dev/null 2>&1 && git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  git diff --check
fi
echo "PASS validação da fundação"
