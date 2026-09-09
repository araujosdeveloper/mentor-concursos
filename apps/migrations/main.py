import hashlib
import logging
import os
import re
from pathlib import Path

import psycopg

MIGRATIONS_DIR = Path(os.getenv("MIGRATIONS_DIR", "/app/database/migrations"))
MIGRATION_PATTERN = re.compile(r"^(?P<version>\d+)_[a-z0-9_]+\.sql$")
LOCK_ID = 687_727_337_110


def connection_parameters() -> dict[str, str | int]:
    return {
        "host": os.environ["DATABASE_HOST"],
        "port": int(os.getenv("DATABASE_PORT", "5432")),
        "dbname": os.environ["DATABASE_NAME"],
        "user": os.environ["DATABASE_USER"],
        "password": os.environ["DATABASE_PASSWORD"],
    }


def apply_migrations() -> None:
    migrations = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if not migrations:
        raise RuntimeError("Nenhuma migração encontrada")

    with psycopg.connect(**connection_parameters(), autocommit=True) as connection:
        connection.execute("SELECT pg_advisory_lock(%s)", (LOCK_ID,))
        try:
            connection.execute("CREATE SCHEMA IF NOT EXISTS mentor_concursos")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS mentor_concursos.schema_migrations (
                    version TEXT PRIMARY KEY,
                    description TEXT NOT NULL,
                    checksum_sha256 TEXT NOT NULL,
                    applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            for path in migrations:
                match = MIGRATION_PATTERN.fullmatch(path.name)
                if match is None:
                    raise RuntimeError(f"Nome de migração inválido: {path.name}")
                version = match.group("version")
                sql = path.read_text(encoding="utf-8")
                checksum = hashlib.sha256(sql.encode()).hexdigest()
                applied = connection.execute(
                    """
                    SELECT checksum_sha256
                    FROM mentor_concursos.schema_migrations
                    WHERE version = %s
                    """,
                    (version,),
                ).fetchone()
                if applied:
                    if applied[0] != checksum:
                        raise RuntimeError(f"Checksum divergente na migração {version}")
                    logging.info("migration_already_applied version=%s", version)
                    continue
                with connection.transaction():
                    connection.execute(sql)
                    connection.execute(
                        """
                        INSERT INTO mentor_concursos.schema_migrations
                            (version, description, checksum_sha256)
                        VALUES (%s, %s, %s)
                        """,
                        (version, path.stem, checksum),
                    )
                logging.info("migration_applied version=%s", version)
        finally:
            connection.execute("SELECT pg_advisory_unlock(%s)", (LOCK_ID,))


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='{"level":"%(levelname)s","message":"%(message)s"}',
    )
    apply_migrations()
