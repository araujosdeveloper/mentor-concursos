#!/bin/sh
set -eu

source_file=/run/secrets/mentor_api_service_token_source
hmac_source_file=/run/secrets/hermes_context_hmac_key_source
runtime_dir=/run/secrets
runtime_file="$runtime_dir/mentor_api_service_token"
hmac_runtime_file="$runtime_dir/hermes_context_hmac_key"

if [ -f "$source_file" ]; then
  cp "$source_file" "$runtime_file"
  chown 10001:10001 "$runtime_file"
  chmod 400 "$runtime_file"
fi

if [ -f "$hmac_source_file" ]; then
  cp "$hmac_source_file" "$hmac_runtime_file"
  chown 10001:10001 "$hmac_runtime_file"
  chmod 400 "$hmac_runtime_file"
fi

exec setpriv --reuid=10001 --regid=10001 --clear-groups -- "$@"
