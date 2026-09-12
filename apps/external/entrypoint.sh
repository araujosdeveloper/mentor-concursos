#!/bin/sh
set -eu

source_file=/run/secrets/jurisprudencias_api_token
runtime_file=/tmp/jurisprudencias_api_token

if [ -f "$source_file" ]; then
  cp "$source_file" "$runtime_file"
  chown 10001:10001 "$runtime_file"
  chmod 400 "$runtime_file"
fi

exec setpriv --reuid=10001 --regid=10001 --clear-groups -- "$@"
