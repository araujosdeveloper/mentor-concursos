import importlib.util
import uuid
from pathlib import Path

import pytest


def module():
    path = Path(__file__).parents[2] / "scripts" / "set-user-role.py"
    spec = importlib.util.spec_from_file_location("set_user_role_test", path)
    assert spec and spec.loader
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


class Transaction:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class Result:
    def __init__(self, row):
        self.row = row

    def fetchone(self):
        return self.row


class Connection:
    def __init__(self, rows):
        self.rows = list(rows)
        self.executed = []

    def transaction(self):
        return Transaction()

    def execute(self, sql, params=()):
        self.executed.append((" ".join(sql.split()), params))
        return Result(self.rows.pop(0) if self.rows else None)


def test_cli_requires_uuid_valid_role_and_confirm():
    script = module()
    valid_id = str(uuid.UUID(int=1))
    invalid_commands = [
        ["--user-id", "nome", "--role", "source_reviewer", "--confirm"],
        ["--user-id", valid_id, "--role", "superuser", "--confirm"],
        ["--user-id", valid_id, "--role", "source_reviewer"],
    ]
    for command in invalid_commands:
        with pytest.raises(SystemExit):
            script.parse_args(command)


def test_role_change_is_transactional_and_audited():
    script = module()
    connection = Connection([{"role": "student"}])
    assert (
        script.set_user_role(connection, user_id=uuid.UUID(int=1), role="source_reviewer")
        == "updated"
    )
    statements = "\n".join(sql for sql, _ in connection.executed)
    assert "FOR UPDATE" in statements
    assert "UPDATE mentor_concursos.users SET role=%s" in statements
    assert "INSERT INTO mentor_concursos.audit_events" in statements


def test_last_admin_cannot_be_demoted():
    script = module()
    connection = Connection([{"role": "admin"}, {"count": 1}])
    with pytest.raises(RuntimeError, match="last_admin"):
        script.set_user_role(connection, user_id=uuid.UUID(int=1), role="student")
    assert not any(sql.startswith("UPDATE") for sql, _ in connection.executed)
