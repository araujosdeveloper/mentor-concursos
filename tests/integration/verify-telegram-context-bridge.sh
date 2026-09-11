#!/usr/bin/env bash
set -euo pipefail

# Exercises the same Hermes subprocess environment factory used by skill/tool
# execution.  Context values are asserted in-process and never printed.
docker exec -i mentor-concursos-hermes python - <<'PY'
import json
import subprocess

from gateway.session_context import clear_session_vars, set_session_vars
from tools.environments.local import hermes_subprocess_env

tokens = set_session_vars(
    platform="telegram",
    user_id="5710991322",
    chat_id="5710991322",
    message_id="bridge-regression",
    session_key="telegram:bridge-regression",
)
try:
    env = hermes_subprocess_env(inherit_credentials=False)
    assert env.get("HERMES_SESSION_PLATFORM") == "telegram"
    assert env.get("HERMES_SESSION_USER_ID") == "5710991322"
    assert env.get("HERMES_SESSION_CHAT_ID") == "5710991322"
    assert env.get("HERMES_SESSION_MESSAGE_ID") == "bridge-regression"
    child = subprocess.run(
        ["python", "/opt/data/skills/mentor-study/scripts/mentor_api.py", "perfil"],
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    profile = json.loads(child.stdout)
    assert profile.get("name") == "Roberto Araujo"
finally:
    clear_session_vars(tokens)
print("telegram context bridge: ok")
PY
