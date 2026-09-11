#!/usr/bin/env python3
"""Altera um papel por UUID em operação administrativa auditável."""

from __future__ import annotations

import argparse
import json
import os
import uuid

import psycopg
from psycopg.rows import dict_row

ROLES = ("student", "operator", "source_reviewer", "admin")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--user-id", type=uuid.UUID, required=True)
    parser.add_argument("--role", choices=ROLES, required=True)
    parser.add_argument("--confirm", action="store_true", required=True)
    return parser.parse_args(argv)


def set_user_role(connection, *, user_id: uuid.UUID, role: str) -> str:
    with connection.transaction():
        target = connection.execute(
            "SELECT role FROM mentor_concursos.users WHERE id=%s FOR UPDATE", (user_id,)
        ).fetchone()
        if not target:
            raise RuntimeError("user_id_not_found")
        old_role = target["role"]
        if old_role == "admin" and role != "admin":
            admin_count = connection.execute(
                "SELECT count(*) AS count FROM mentor_concursos.users WHERE role='admin'"
            ).fetchone()["count"]
            if admin_count <= 1:
                raise RuntimeError("last_admin_role_change_forbidden")
        if old_role == role:
            return "unchanged"
        connection.execute("UPDATE mentor_concursos.users SET role=%s WHERE id=%s", (role, user_id))
        request_id = f"set-user-role-{uuid.uuid4()}"
        connection.execute(
            """INSERT INTO mentor_concursos.audit_events
               (actor,action,entity,entity_id,request_id,metadata)
               VALUES ('administrative-script','user_role_changed','users',%s,%s,%s)""",
            (user_id, request_id, json.dumps({"old_role": old_role, "new_role": role})),
        )
    return "updated"


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    connection = psycopg.connect(
        host=os.environ["DATABASE_HOST"],
        port=int(os.getenv("DATABASE_PORT", "5432")),
        dbname=os.environ["DATABASE_NAME"],
        user=os.environ["DATABASE_USER"],
        password=os.environ["DATABASE_PASSWORD"],
        row_factory=dict_row,
    )
    with connection:
        result = set_user_role(connection, user_id=args.user_id, role=args.role)
    print(json.dumps({"status": result, "user_id": str(args.user_id), "role": args.role}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
