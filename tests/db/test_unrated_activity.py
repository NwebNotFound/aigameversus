"""Models that played finished matches no rating counted: shown with a reason, never with an Elo."""

import asyncio
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from arena.api.app import app
from arena.db.database import connect, migrate


def seat(model):
    return {"kind": "model", "model_id": model, "name": model}


BOT = {"kind": "bot", "model_id": None, "name": "Random Bot"}


async def add(pool, game, seats, *, status="finished", rated=False):
    match_id = uuid4()
    await pool.execute(
        "INSERT INTO matches (id, game, status, players, seed, settings, seats) "
        "VALUES ($1, $2, $3, $4, 1, '{}', $5)",
        match_id,
        game,
        status,
        list(seats),
        seats,
    )
    if rated:
        await pool.execute(
            "INSERT INTO rated_matches (match_id, game_id) VALUES ($1, $2)", match_id, game
        )
    return match_id


def table(*models):
    return {f"p{i}": seat(m) for i, m in enumerate(models, start=1)}


@pytest.fixture
def client(database_url, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", database_url)

    async def seed():
        pool = await connect(database_url)
        try:
            await migrate(pool)
            # W2: gpt-luna and claude-haiku repeat, four guests once each: nothing is rated
            await add(
                pool,
                "werewolf",
                table(
                    "gpt-luna", "gpt-luna", "claude-haiku", "claude-haiku", "g1", "g2", "g3", "g4"
                ),
            )
            # two distinct models, rated; the same pair once more, unrated for another reason
            await add(pool, "poker", table("gpt-luna", "claude-haiku"), rated=True)
            await add(pool, "poker", table("gpt-luna", "claude-haiku"))
            # one model among random bots: nobody to rank it against
            await add(pool, "poker", {"p1": seat("solo"), "p2": BOT, "p3": BOT})
            # not finished: not activity yet
            await add(pool, "poker", table("busy", "other"), status="running")
            await add(pool, "poker", table("broken", "other"), status="failed")
        finally:
            await pool.close()

    asyncio.run(seed())
    with TestClient(app) as client:
        yield client


def rows(client, **params):
    board = client.get("/leaderboard", params={"kind": "models", **params}).json()
    return {(u["model_id"], u["game"]): u for u in board["unrated"]}


def test_the_w2_table_shows_every_model_that_sat_there_with_why(client):
    found = rows(client, game="werewolf")

    assert set(found) == {
        (m, "werewolf") for m in ("gpt-luna", "claude-haiku", "g1", "g2", "g3", "g4")
    }
    luna = found[("gpt-luna", "werewolf")]
    assert (luna["matches_played"], luna["matches_rated"], luna["matches_unrated"]) == (1, 0, 1)
    assert luna["reason"] == "duplicate_model" and "several seats" in luna["text"]["en"]
    guest = found[("g1", "werewolf")]
    assert guest["reason"] == "table_repeats_a_model"
    assert "another model" in guest["text"]["en"] and guest["text"]["de"]


def test_a_model_with_rated_and_unrated_matches_shows_both_counts(client):
    found = rows(client, game="poker")

    luna = found[("gpt-luna", "poker")]
    assert (luna["matches_played"], luna["matches_rated"]) == (2, 1)
    assert luna["reasons"] == {"not_rated": 1}  # two distinct models, no recorded reason


def test_one_model_among_bots_is_unrated_for_want_of_a_second_model(client):
    solo = rows(client, game="poker")[("solo", "poker")]

    assert solo["reason"] == "fewer_than_two_models" and solo["matches_rated"] == 0


def test_running_and_failed_matches_are_not_activity(client):
    found = rows(client)

    assert not any(model in ("busy", "broken", "other") for model, _ in found)


def test_without_a_game_every_game_is_listed_and_a_game_filters(client):
    assert {game for _, game in rows(client)} == {"werewolf", "poker"}
    assert {game for _, game in rows(client, game="werewolf")} == {"werewolf"}


def test_no_rating_is_ever_made_up_and_bots_get_no_list(client):
    board = client.get("/leaderboard", params={"kind": "models"}).json()
    assert all("rating" not in u and "elo" not in u for u in board["unrated"])
    assert board["rows"] == []  # nobody is rated in this seed: the list is not a rating
    assert client.get("/leaderboard", params={"kind": "bots"}).json()["unrated"] == []


def test_the_model_page_of_a_guest_without_a_profile_lists_its_unrated_matches(client):
    page = client.get("/models/g1")

    assert page.status_code == 200
    body = page.json()
    assert body["overall"] is None and body["games"] == []
    assert [(u["game"], u["matches_played"], u["reason"]) for u in body["unrated"]] == [
        ("werewolf", 1, "table_repeats_a_model")
    ]
    assert client.get("/models/never-seen").status_code == 404
