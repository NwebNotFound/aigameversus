"""GET /ledger/month: what this calendar month has cost, for the new-match form."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from arena.api.app import app
from arena.config import load_config
from arena.db.database import connect, migrate


@pytest.fixture
def client(database_url, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", database_url)
    with TestClient(app) as client:
        yield client


def book(database_url, calls):
    async def run():
        pool = await connect(database_url)
        try:
            await migrate(pool)
            for called_at, cost in calls:
                await pool.execute(
                    "INSERT INTO model_calls (match_id, player, model, called_at, cost_micro_eur) "
                    "VALUES ($1, 'p1', 'mock', $2, $3)",
                    uuid4(),
                    called_at,
                    cost,
                )
        finally:
            await pool.close()

    asyncio.run(run())


def test_the_month_counts_only_its_own_calls(client, database_url):
    now = datetime.now(UTC)
    last_month = now.replace(day=1) - timedelta(days=1)
    book(database_url, [(now, 120_000), (now, 30_000), (last_month, 9_000_000)])

    month = client.get("/ledger/month").json()

    cap = int(load_config().limits.month_eur * 1_000_000)
    assert month == {
        "month": now.strftime("%Y-%m"),
        "spent_micro_eur": 150_000,
        "cap_micro_eur": cap,
        "remaining_micro_eur": cap - 150_000,
    }


def test_nothing_remains_past_the_cap(client, database_url):
    cap = int(load_config().limits.month_eur * 1_000_000)
    book(database_url, [(datetime.now(UTC), cap + 5)])

    assert client.get("/ledger/month").json()["remaining_micro_eur"] == 0
