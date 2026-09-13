#!/bin/sh
set -eu

readonly TELEGRAM_SECRET=/run/secrets/telegram_bot_token
readonly API_SECRET=/run/secrets/mentor_api_service_token
readonly HMAC_SECRET=/run/secrets/hermes_context_hmac_key
readonly DATA_DIR=/opt/data

fail() {
  echo "mentor-hermes-entrypoint: configuração de segredo ausente ou inválida" >&2
  exit 78
}

[ -s "$TELEGRAM_SECRET" ] || fail
[ -s "$API_SECRET" ] || fail
[ -s "$HMAC_SECRET" ] || fail

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
# Docker's source secret remains root-only.  Materialize a short-lived copy in
# the container's /run tmpfs for the non-root Hermes process only.
HMAC_RUNTIME_DIR=/run/mentor-secrets
install -d -m 0700 -o hermes -g hermes "$HMAC_RUNTIME_DIR"
HMAC_RUNTIME_SECRET="$HMAC_RUNTIME_DIR/hermes_context_hmac_key"
install -m 0400 -o hermes -g hermes "$HMAC_SECRET" "$HMAC_RUNTIME_SECRET"
export MENTOR_CONTEXT_HMAC_KEY_FILE="$HMAC_RUNTIME_SECRET"
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
  inicio: {type: alias, target: "mentor-study /inicio"}
  ajuda: {type: alias, target: "mentor-study /ajuda"}
  perguntar: {type: alias, target: "mentor-study /perguntar"}
  perfil: {type: alias, target: "mentor-study /perfil"}
  progresso: {type: alias, target: "mentor-study /progresso"}
  estudar: {type: alias, target: "mentor-study /estudar"}
  pausar: {type: alias, target: "mentor-study /pausar"}
  retomar: {type: alias, target: "mentor-study /retomar"}
  finalizar: {type: alias, target: "mentor-study /finalizar"}
  cancelar: {type: alias, target: "mentor-study /cancelar"}
  questao: {type: alias, target: "mentor-study /questao"}
  responder: {type: alias, target: "mentor-study /responder"}
  simulado: {type: alias, target: "mentor-study /simulado"}
  revisar: {type: alias, target: "mentor-study /revisar"}
  erros: {type: alias, target: "mentor-study /erros"}
  desempenho: {type: alias, target: "mentor-study /desempenho"}
EOF
fi

# Reconcile all managed study aliases in an existing dedicated profile. The
# original slash command is part of the target so the skill receives an
# explicit operation instead of entering its generic conversational mode.
# Only missing entries are appended; existing entries are never rewritten, so
# multiline entries from older profiles remain valid YAML.
for command_name in inicio ajuda perguntar perfil progresso estudar pausar retomar finalizar cancelar questao responder simulado revisar erros desempenho; do
  if ! grep -q "^  ${command_name}:" "$DATA_DIR/config.yaml"; then
    printf '  %s: {type: alias, target: "mentor-study /%s"}\n' "$command_name" "$command_name" >> "$DATA_DIR/config.yaml"
  fi
done

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
    elif [ "$relative_path" = "mentor-study/scripts/mentor_api.py" ] || [ "$relative_path" = "mentor-study/SKILL.md" ]; then
      # These project-owned routing contracts are safe to reconcile on every
      # restart; OAuth, pairing, memory and operator files remain untouched.
      if ! cmp -s "$source_path" "$target_path"; then
        install -m 0600 "$source_path" "$target_path"
      fi
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
