#!/usr/bin/env bash
set -euo pipefail

# Controlled regression for Telegram practice-command routing.  It uses the
# already authorized test context, creates one question through the real API,
# and removes that exact temporary record before exiting.
root=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
cd "$root"

for command in questao responder simulado revisar erros desempenho; do
  grep -Eq "^  ${command}: \{type: alias, target: \"mentor-study /${command}\"\}$" \
    infra/hermes/config.yaml
done
grep -q 'args.action == "questao"' infra/hermes/skills/mentor-study/scripts/mentor_api.py
grep -q 'POST", "/api/v1/practice/question"' infra/hermes/skills/mentor-study/scripts/mentor_api.py
grep -q 'instrução explícita' infra/hermes/skills/mentor-study/SKILL.md

context=(
  -e HERMES_SESSION_PLATFORM=telegram
  -e HERMES_SESSION_USER_ID="${MENTOR_TEST_TELEGRAM_ID:?set MENTOR_TEST_TELEGRAM_ID}"
  -e HERMES_SESSION_CHAT_ID="${MENTOR_TEST_TELEGRAM_ID}"
  -e HERMES_SESSION_MESSAGE_ID="practice-routing-$(date +%s%N)"
)
result=$(docker exec "${context[@]}" mentor-concursos-hermes \
  python /opt/data/skills/mentor-study/scripts/mentor_api.py questao)
qid=$(printf '%s' "$result" | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d.get("id"); assert d.get("prompt"); assert len(d.get("alternatives", [])) in (4, 5); assert "Modo de estudo ativo" not in json.dumps(d); print(d["id"])')

cleanup() {
  docker compose exec -T mentor-concursos-postgres psql -U mentor_app -d mentor_concursos \
    -v ON_ERROR_STOP=1 -c "DELETE FROM mentor_concursos.practice_questions WHERE id='$qid';" >/dev/null
}
trap cleanup EXIT

echo "practice routing and question contract: ok"
