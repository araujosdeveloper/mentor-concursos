#!/usr/bin/env bash
set -Eeuo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."
command -v pip-compile >/dev/null 2>&1 || {
  echo "FAIL pip-compile indisponível" >&2
  exit 1
}
export PIP_TOOLS_CACHE_DIR="${PIP_TOOLS_CACHE_DIR:-/tmp/mentor-concursos-pip-tools-cache}"

lock_tmp_dir="$(mktemp -d)"
runtime_lock="$lock_tmp_dir/requirements.lock"
dev_lock="$lock_tmp_dir/requirements-dev.lock"
cp requirements.lock "$runtime_lock"
cp requirements-dev.lock "$dev_lock"
trap 'rm -rf "$lock_tmp_dir"' EXIT

pip-compile --quiet --resolver=backtracking --allow-unsafe --generate-hashes --strip-extras --no-header \
  --no-emit-index-url --output-file "$runtime_lock" pyproject.toml
pip-compile --quiet --resolver=backtracking --allow-unsafe --extra dev --generate-hashes --strip-extras --no-header \
  --no-emit-index-url --output-file "$dev_lock" pyproject.toml

cmp --silent requirements.lock "$runtime_lock" || {
  echo "FAIL requirements.lock diverge de pyproject.toml" >&2
  exit 1
}
cmp --silent requirements-dev.lock "$dev_lock" || {
  echo "FAIL requirements-dev.lock diverge de pyproject.toml" >&2
  exit 1
}
echo "PASS lockfiles sincronizados"
