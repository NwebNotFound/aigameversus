"""Connection pool and schema migrations for Postgres."""

import json
import os
from importlib import resources

import asyncpg

_MIGRATIONS = resources.files("arena.db") / "migrations"
_MIGRATION_LOCK = 7_240_001  # advisory lock id: only one process migrates at a time


async def _use_json_for_jsonb(connection: asyncpg.Connection) -> None:
    await connection.set_type_codec(
        "jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog"
    )


async def connect(url: str, *, min_size: int = 1) -> asyncpg.Pool:
    """Open a pool. Close it with `await pool.close()`.

    With `min_size=0` it opens no connection yet, so a server that is down
    fails the first query instead of this call.
    """
    return await asyncpg.create_pool(
        url, init=_use_json_for_jsonb, min_size=min_size, max_size=10, timeout=5
    )


def ledger_url(database_url: str) -> str:
    """Where the spend ledger is kept: LEDGER_DATABASE_URL, else the match database."""
    return os.environ.get("LEDGER_DATABASE_URL") or database_url


async def migrate(pool: asyncpg.Pool) -> list[str]:
    """Apply the migrations that have not run yet, in file-name order.

    All of them run in one transaction. Returns the names that were applied.
    """
    async with pool.acquire() as connection, connection.transaction():
        await connection.execute("SELECT pg_advisory_xact_lock($1)", _MIGRATION_LOCK)
        await connection.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            "name text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())"
        )
        done = {row["name"] for row in await connection.fetch("SELECT name FROM schema_migrations")}
        files = sorted(
            (file for file in _MIGRATIONS.iterdir() if file.name.endswith(".sql")),
            key=lambda file: file.name,
        )
        applied = []
        for file in files:
            if file.name not in done:
                await connection.execute(file.read_text(encoding="utf-8"))
                await connection.execute(
                    "INSERT INTO schema_migrations (name) VALUES ($1)", file.name
                )
                applied.append(file.name)
        return applied
