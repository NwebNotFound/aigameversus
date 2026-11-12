"""GET /matches: the game filter, paging with a total count, and the outcome line of each row."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from arena.api.app import app
from arena.db.database import connect, migrate

START = datetime(2026, 11, 1, tzinfo=UTC)


@pytest.fixture
def client(database_url, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", database_url)

    async def seed():
        pool = await connect(database_url)
        try:
            await migrate(pool)
            for i in range(30):  # oldest first: i grows with the start time
                game = ["liars_deck", "poker", "werewolf"][i % 3]
                status = "finished"
                await pool.execute(
                    "INSERT INTO matches (id, game, status, players, seed, settings, started_at, "
                    "placements) VALUES ($1, $2, $3, $4, 1, '{}', $5, $6)",
                    uuid4(),
                    game,
                    status,
                    ["p1", "p2"],
                    START + timedelta(minutes=i),
                    None
                    if status == "running"
                    else [{"player": "p1", "rank": 1}, {"player": "p2", "rank": 2}],
                )
        finally:
            await pool.close()

    asyncio.run(seed())
    with TestClient(app) as client:
        yield client


def test_the_game_filter_returns_only_that_game_and_its_total(client):
    answer = client.get("/matches", params={"game": "poker"})

    assert answer.status_code == 200
    assert {m["game"] for m in answer.json()} == {"poker"}
    assert answer.headers["x-total-count"] == "10" and len(answer.json()) == 10


def test_paging_walks_the_list_newest_first_without_gaps_or_repeats(client):
    first = client.get("/matches", params={"limit": 12}).json()
    second = client.get("/matches", params={"limit": 12, "offset": 12}).json()
    rest = client.get("/matches", params={"limit": 12, "offset": 24}).json()

    ids = [m["id"] for m in first + second + rest]
    assert len(ids) == 30 == len(set(ids))
    starts = [m["started_at"] for m in first + second + rest]
    assert starts == sorted(starts, reverse=True)
    assert client.get("/matches", params={"limit": 12}).headers["x-total-count"] == "30"


def test_the_default_page_and_the_limits(client):
    assert len(client.get("/matches").json()) == 30  # a page holds up to 100
    assert client.get("/matches", params={"limit": 0}).status_code == 422
    assert client.get("/matches", params={"limit": 501}).status_code == 422
    assert client.get("/matches", params={"offset": -1}).status_code == 422
    assert client.get("/matches", params={"offset": 99}).json() == []


def test_filters_combine_and_each_row_has_its_outcome(client):
    rows = client.get("/matches", params={"game": "werewolf", "status": "finished"}).json()

    assert rows and all(m["game"] == "werewolf" and m["status"] == "finished" for m in rows)
    assert all(m["outcome"]["kind"] == "won" and m["outcome"]["winners"] == ["p1"] for m in rows)
    assert rows[0]["outcome"]["text"] == {"en": "Bot 1 won", "de": "Bot 1 gewann"}


def test_a_running_match_row_shows_no_result(client, database_url):
    async def start_one():  # after startup: the app marks matches found running as interrupted
        pool = await connect(database_url)
        try:
            await pool.execute(
                "INSERT INTO matches (id, game, status, players, seed, settings, started_at) "
                "VALUES ($1, 'poker', 'running', $2, 1, '{}', now())",
                uuid4(),
                ["p1", "p2"],
            )
        finally:
            await pool.close()

    asyncio.run(start_one())
    running = client.get("/matches", params={"status": "running"}).json()

    assert len(running) == 1
    assert running[0]["outcome"] == {
        "kind": "running",
        "winners": [],
        "text": {"en": "In progress", "de": "Läuft"},
    }
