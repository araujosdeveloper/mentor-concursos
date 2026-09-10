#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."

runner="/opt/data/skills/mentor-study/scripts/mentor_api.py"
telegram_id="${MENTOR_TEST_TELEGRAM_ID:?MENTOR_TEST_TELEGRAM_ID must identify the already-authorized test user}"

result=$(docker exec mentor-concursos-hermes python "$runner" perguntar \
  --telegram-user-id "$telegram_id" --query 'O que diz a base sobre teletransporte quântico?')
python3 -c 'import json,sys; d=json.loads(sys.argv[1]); assert d["state"] == "insufficient_evidence"; assert not d["citations"]; assert "teletransporte" not in d["answer"].lower(); print("PASS consulta fora da base sem fallback externo")' "$result"

result=$(docker exec mentor-concursos-hermes python "$runner" perguntar \
  --telegram-user-id "$telegram_id" --query 'O que estabelece o artigo 1º da Lei 9.784?')
python3 -c 'import json,sys; d=json.loads(sys.argv[1]); assert d["state"] == "answered"; assert d["citations"]; print("PASS consulta fundamentada com citações")' "$result"

result=$(docker exec mentor-concursos-hermes python "$runner" perfil \
  --telegram-user-id 999999999 || true)
python3 -c 'import json,sys; d=json.loads(sys.argv[1]); assert "error" in d; print("PASS usuário Telegram não autorizado")' "$result"

if docker exec -e MENTOR_API_BASE_URL=http://mentor-concursos-api:65530 mentor-concursos-hermes \
  python "$runner" perguntar --telegram-user-id "$telegram_id" --query 'O que estabelece o artigo 1º da Lei 9.784?' >/tmp/mentor-routing-api-fail.out; then
  echo "FAIL API indisponível não foi tratada" >&2
  exit 1
fi
grep -q 'API indisponível' /tmp/mentor-routing-api-fail.out
echo "PASS API indisponível sem resposta parcial"
