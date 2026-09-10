#!/bin/sh
set -eu

readonly TELEGRAM_SECRET=/run/secrets/telegram_bot_token
readonly API_SECRET=/run/secrets/mentor_api_service_token
readonly DATA_DIR=/opt/data

fail() {
  echo "mentor-hermes-entrypoint: configuração de segredo ausente ou inválida" >&2
  exit 78
}

[ -s "$TELEGRAM_SECRET" ] || fail
[ -s "$API_SECRET" ] || fail

# The token is read only into the process environment required by Hermes. It is
# never echoed, persisted, passed as a Compose value, or included in inspect
# metadata. Docker mounts both source files read-only at /run/secrets.
TELEGRAM_BOT_TOKEN="$(cat "$TELEGRAM_SECRET")"
case "$TELEGRAM_BOT_TOKEN" in
  *[![:print:]]*|*' '*|*'	'*) fail ;;
esac
export TELEGRAM_BOT_TOKEN
API_RUNTIME_SECRET=/run/mentor_api_service_token
install -m 0400 -o hermes -g hermes "$API_SECRET" "$API_RUNTIME_SECRET"
export MENTOR_API_SERVICE_TOKEN_FILE="$API_RUNTIME_SECRET"
export HERMES_HOME="$DATA_DIR"
export HOME="$DATA_DIR/home"

umask 077
mkdir -p "$DATA_DIR" "$DATA_DIR/memories" "$DATA_DIR/home"

# Seed only the dedicated profile. Existing files are never overwritten, which
# preserves OAuth state, pairing state and operator edits across restarts.
seed_file() {
  source_path=$1
  target_path=$2
  if [ ! -e "$target_path" ]; then
    install -m 0600 "$source_path" "$target_path"
  fi
}

seed_file /opt/mentor-hermes/config.yaml "$DATA_DIR/config.yaml"
seed_file /opt/mentor-hermes/SOUL.md "$DATA_DIR/SOUL.md"
seed_file /opt/mentor-hermes/AGENTS.md "$DATA_DIR/AGENTS.md"
seed_file /opt/mentor-hermes/USER.md "$DATA_DIR/memories/USER.md"
seed_file /opt/mentor-hermes/MEMORY.md "$DATA_DIR/memories/MEMORY.md"

# Existing dedicated profiles predate the study aliases. Add the managed block
# once, without touching OAuth, pairing, sessions or operator configuration.
if ! grep -q '^quick_commands:' "$DATA_DIR/config.yaml"; then
  cat >> "$DATA_DIR/config.yaml" <<'EOF'

quick_commands:
  inicio: {type: alias, target: mentor-study}
  ajuda: {type: alias, target: mentor-study}
  perguntar: {type: alias, target: mentor-study}
  perfil: {type: alias, target: mentor-study}
  progresso: {type: alias, target: mentor-study}
  estudar: {type: alias, target: mentor-study}
  pausar: {type: alias, target: mentor-study}
  retomar: {type: alias, target: mentor-study}
  finalizar: {type: alias, target: mentor-study}
  cancelar: {type: alias, target: mentor-study}
EOF
fi

# The study skill is project-owned and communicates only with the internal API.
# Seed it without overwriting operator state across restarts.
if [ -d /opt/mentor-hermes/skills ]; then
  mkdir -p "$DATA_DIR/skills"
  find /opt/mentor-hermes/skills -type f | while IFS= read -r source_path; do
    relative_path=${source_path#/opt/mentor-hermes/skills/}
    target_path="$DATA_DIR/skills/$relative_path"
    mkdir -p "$(dirname "$target_path")"
    if [ ! -e "$target_path" ]; then
      install -m 0600 "$source_path" "$target_path"
    fi
  done
fi

# The vendor image runs the gateway as the bundled hermes user. Keep the
# entire dedicated state readable/writable only by that account.
chown -R hermes:hermes "$DATA_DIR"

if [ "$#" -gt 0 ]; then
  exec gosu hermes "$@"
fi

# Retain the approved image's s6 supervision, but do not enable its optional
# dashboard. The dashboard would require a separate auth provider and is not
# part of this phase; Telegram polling is the only inbound surface.
export HERMES_DASHBOARD=0
export HERMES_DASHBOARD_HOST=127.0.0.1
exec /init /opt/hermes/docker/main-wrapper.sh gateway run
