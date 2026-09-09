#!/usr/bin/env bash
set -Eeuo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."
command -v pip-compile >/dev/null 2>&1 || {
  echo "FAIL pip-compile indisponível; use um ambiente virtual local com pip-tools==7.6.1" >&2
  exit 1
}
export PIP_TOOLS_CACHE_DIR="${PIP_TOOLS_CACHE_DIR:-/tmp/mentor-concursos-pip-tools-cache}"

pip-compile --quiet --upgrade --resolver=backtracking --allow-unsafe --generate-hashes \
  --strip-extras --no-header --no-emit-index-url \
  --output-file requirements.lock pyproject.toml
pip-compile --quiet --upgrade --resolver=backtracking --allow-unsafe --extra dev --generate-hashes \
  --strip-extras --no-header --no-emit-index-url \
  --output-file requirements-dev.lock pyproject.toml

echo "Lockfiles atualizados; revise o diff, execute testes e pip-audit antes do commit."
