#!/usr/bin/env bash
set -Eeuo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."
umask 077

command -v openssl >/dev/null 2>&1 || {
  echo "ERRO: openssl não está disponível" >&2
  exit 1
}

mkdir -p secrets
chmod 700 secrets

if [[ ! -e .env ]]; then
  postgres_password="$(openssl rand -hex 32)"
  redis_password="$(openssl rand -hex 32)"
  {
    printf '%s\n' 'POSTGRES_DB=mentor_concursos'
    printf '%s\n' 'POSTGRES_USER=mentor_app'
    printf 'POSTGRES_PASSWORD=%s\n' "$postgres_password"
    printf 'REDIS_PASSWORD=%s\n' "$redis_password"
    printf '%s\n' 'APP_ENV=production' 'LOG_LEVEL=INFO' 'TZ=America/Sao_Paulo' 'REQUIRE_SIGNED_CONTEXT=true'
  } >.env
fi
chmod 600 .env

token_file="secrets/mentor_api_service_token"
if [[ ! -e "$token_file" ]]; then
  openssl rand -hex 32 >"$token_file"
fi
chmod 600 "$token_file"

hmac_file="secrets/hermes_context_hmac_key"
if [[ ! -e "$hmac_file" ]]; then
  openssl rand -hex 32 >"$hmac_file"
fi
chmod 600 "$hmac_file"

git check-ignore -q .env && git check-ignore -q "$token_file" && git check-ignore -q "$hmac_file" || {
  echo "ERRO: segredo local não está protegido pelo .gitignore" >&2
  exit 1
}
if git ls-files --error-unmatch .env "$token_file" "$hmac_file" >/dev/null 2>&1; then
  echo "ERRO: segredo local rastreado pelo Git" >&2
  exit 1
fi

echo "Ambiente local preparado sem exibir segredos."
