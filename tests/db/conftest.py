"""Database tests run against a real Postgres, each test in its own schema.

Start one with `docker compose up -d db`. Without a reachable server the tests
are skipped locally and fail in CI.
"""

import asyncio
import os
from uuid import uuid4

import asyncpg
import pytest

DEFAULT_URL = "postgresql://arena:arena_dev@127.0.0.1:5433/arena"


async def _execute(url: str, statement: str) -> None:
    connection = await asyncpg.connect(url, timeout=3)
    try:
        await connection.execute(statement)
    finally:
        await connection.close()


def _empty_schema():
    url = os.environ.get("ARENA_TEST_DATABASE_URL", DEFAULT_URL)
    schema = f"test_{uuid4().hex}"
    try:
        asyncio.run(_execute(url, f'CREATE SCHEMA "{schema}"'))
    except (OSError, TimeoutError, asyncpg.PostgresError) as error:
        if os.environ.get("CI"):
            raise
        pytest.skip(f"Postgres is not reachable ({type(error).__name__})")
    yield f"{url}?search_path={schema}"
    asyncio.run(_execute(url, f'DROP SCHEMA "{schema}" CASCADE'))


@pytest.fixture
def database_url():
    """URL of an empty schema that is dropped after the test."""
    yield from _empty_schema()


@pytest.fixture
def other_database_url():
    """A second empty schema, for a database of its own such as the spend ledger."""
    yield from _empty_schema()
