#!/bin/sh
set -eu

copy_secret() {
  source_file="$1"
  runtime_file="$2"
  if [ -f "$source_file" ]; then
    cp "$source_file" "$runtime_file"
    chown 10001:10001 "$runtime_file"
    chmod 400 "$runtime_file"
  fi
}

copy_secret /run/secrets/jurisprudencias_api_token /tmp/jurisprudencias_api_token
copy_secret /run/secrets/tavily_api_key /tmp/tavily_api_key

exec setpriv --reuid=10001 --regid=10001 --clear-groups -- "$@"
