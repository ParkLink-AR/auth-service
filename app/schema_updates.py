"""Schema changes for databases created before a model gained them.

There's no migration history here (main.py builds the schema with create_all, which never
touches a table that already exists), so a column or enum value added to an existing model
has to be added to already-deployed databases by hand -- that's this module, run once at
startup. Every statement is idempotent. Postgres only: tests use a fresh SQLite database
that create_all already builds complete.
"""

from loguru import logger
from sqlalchemy import text
from sqlalchemy.engine import Engine

_USER_COLUMNS = {
    "suspended_at": "TIMESTAMPTZ",
    "suspended_by_admin_id": "UUID",
    "suspension_reason": "VARCHAR(500)",
    "deletion_requested_at": "TIMESTAMPTZ",
    "deletion_scheduled_at": "TIMESTAMPTZ",
    "deletion_requested_by_admin_id": "UUID",
    "deletion_reason": "VARCHAR(500)",
    "deleted_at": "TIMESTAMPTZ",
}


def apply_schema_updates(engine: Engine) -> None:
    if engine.dialect.name != "postgresql":
        return
    # ALTER TYPE ... ADD VALUE can't run inside a transaction block on every Postgres
    # version, so this runs in autocommit.
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        connection.execute(text("ALTER TYPE user_status ADD VALUE IF NOT EXISTS 'PENDING_DELETION'"))
        for column, column_type in _USER_COLUMNS.items():
            connection.execute(text(f"ALTER TABLE users ADD COLUMN IF NOT EXISTS {column} {column_type}"))
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_users_deletion_scheduled_at "
                "ON users (deletion_scheduled_at) WHERE status = 'PENDING_DELETION'"
            )
        )
    logger.info("[STARTUP] Esquema de users actualizado (ciclo de vida de cuentas)")
