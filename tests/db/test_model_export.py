"""GET /models/{id}/export: one model's matches as CSV, public facts and counts only."""

import asyncio
import csv
import io
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from arena.api.app import app
from arena.db.database import connect, migrate


def seat(model):
    return {"kind": "model", "model_id": model, "name": model}


BOT = {"kind": "bot", "model_id": None, "name": "Random Bot"}


async def add(pool, seats, ranks, *, status="finished", rated=False):
    match_id = uuid4()
    await pool.execute(
        "INSERT INTO matches (id, game, status, players, seed, settings, seats, placements, "
        "prompt_version, finished_at) VALUES ($1, 'poker', $2, $3, 77, '{}', $4, $5, 'p2', now())",
        match_id,
        status,
        list(seats),
        seats,
        [{"player": p, "rank": r} for p, r in ranks.items()] if ranks else None,
    )
    if rated:
        await pool.execute(
            "INSERT INTO rated_matches (match_id, game_id) VALUES ($1, 'poker')", match_id
        )
    return match_id


@pytest.fixture
def client(database_url, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", database_url)
    ids = {}

    async def seed():
        pool = await connect(database_url)
        try:
            await migrate(pool)
            two = {"p1": seat("glm-flash"), "p2": seat("deepseek-flash")}
            ids["won"] = await add(pool, two, {"p1": 1, "p2": 2}, rated=True)
            ids["lost"] = await add(
                pool, {"p1": seat("deepseek-flash"), "p2": seat("glm-flash")}, {"p1": 1, "p2": 2}
            )
            ids["bots"] = await add(pool, {"p1": seat("glm-flash"), "p2": BOT}, {"p1": 1, "p2": 2})
            ids["failed"] = await add(pool, two, None, status="failed")
            await pool.execute(
                "INSERT INTO model_calls (match_id, player, model, called_at, cost_micro_eur) "
                "VALUES ($1, 'p1', 'glm-flash', now(), 6000)",
                ids["won"],
            )
            for seq, (kind, data) in enumerate(
                [("action_accepted", {"player": "p1"})] * 3
                + [
                    ("action_rejected", {"player": "p1"}),
                    ("decision", {"player": "p1", "fallback": "random"}),
                    ("action_accepted", {"player": "p2"}),
                ]
            ):
                await pool.execute(
                    "INSERT INTO match_events (match_id, seq, source, type, data, visible_to) "
                    "VALUES ($1, $2, 'engine', $3, $4, '{}')",
                    ids["won"],
                    seq,
                    kind,
                    data,
                )
        finally:
            await pool.close()

    asyncio.run(seed())
    with TestClient(app) as client:
        client.ids = ids
        yield client


def rows(client, model="glm-flash"):
    response = client.get(f"/models/{model}/export")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    return list(csv.DictReader(io.StringIO(response.text)))


def test_one_row_per_seat_of_the_model_including_failed_ones(client):
    found = rows(client)

    assert len(found) == 4
    assert {r["match_id"] for r in found} == {
        str(client.ids[k]) for k in ("won", "lost", "bots", "failed")
    }


def test_a_row_has_the_result_the_counts_the_cost_and_the_opponents(client):
    won = next(r for r in rows(client) if r["match_id"] == str(client.ids["won"]))

    assert (won["seat"], won["rank"], won["won"], won["rated"]) == ("p1", "1", "1", "1")
    assert (won["players"], won["opponents"], won["prompt_version"]) == (
        "2",
        "deepseek-flash",
        "p2",
    )
    assert (won["answers_accepted"], won["answers_rejected"], won["fallback_moves"]) == (
        "3",
        "1",
        "1",
    )
    assert won["cost_micro_eur"] == "6000" and won["unrated_reason"] == ""


def test_an_unrated_match_says_why_and_has_no_rating(client):
    bots = next(r for r in rows(client) if r["match_id"] == str(client.ids["bots"]))
    lost = next(r for r in rows(client) if r["match_id"] == str(client.ids["lost"]))

    assert (bots["rated"], bots["unrated_reason"], bots["opponents"]) == (
        "0",
        "fewer_than_two_models",
        "bot",
    )
    assert bots["rating_before"] == "" and bots["cost_micro_eur"] == "0"
    assert (lost["seat"], lost["won"], lost["unrated_reason"]) == ("p2", "0", "not_rated")


def test_the_file_holds_no_seed(client):
    assert "77" not in client.get("/models/glm-flash/export").text.split("\n", 1)[0]
    assert "seed" not in client.get("/models/glm-flash/export").text


def test_a_configured_model_without_matches_gets_the_header_only(client):
    assert rows(client, "qwen-flash") == []
    assert client.get("/models/qwen-flash/export").text.startswith("match_id,game,")


def test_an_unknown_model_is_404(client):
    assert client.get("/models/no-such-model/export").status_code == 404


def test_cells_that_look_like_formulas_are_quoted_and_the_file_name_is_plain():
    from arena.api.model_export import safe

    assert safe("=SUM(A1)") == "'=SUM(A1)" and safe("@x") == "'@x" and safe("-1+2") == "'-1+2"
    assert safe("glm-flash") == "glm-flash" and safe(5) == 5 and safe("") == ""


def test_the_file_name_has_only_plain_characters(client):
    name = client.get("/models/glm-flash/export").headers["content-disposition"]

    assert name == 'attachment; filename="aigameversus-glm-flash.csv"'
