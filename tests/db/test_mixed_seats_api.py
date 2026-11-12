"""Mixed tables through POST /matches `seats`: models and random bots at one table.

LiteLLM answers from its own mock (fixture `answer_with`): nothing reaches a provider.
"""

import asyncio

import pytest
from fastapi.testclient import TestClient

from arena.api.app import app
from arena.db.database import connect
from tests.db.test_model_seats_api import KEY, finish

NO_TOOL = {"mock_response": "I think so."}  # no tool call: the engine falls back to a random move


@pytest.fixture
def client(database_url, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("ARENA_ALLOW_MODEL_SEATS", "1")
    monkeypatch.setenv("OPENROUTER_API_KEY", KEY)
    with TestClient(app) as client:
        yield client


def rows(database_url, query, *args):
    async def read():
        pool = await connect(database_url)
        try:
            return [tuple(row) for row in await pool.fetch(query, *args)]
        finally:
            await pool.close()

    return asyncio.run(read())


def model(model_id):
    return {"kind": "model", "model": model_id}


BOT = {"kind": "bot"}


def test_a_liars_deck_table_of_two_models_and_two_bots_books_and_rates_the_models_only(
    client, database_url, answer_with
):
    answer_with(**NO_TOOL)
    seats = [model("glm-flash"), BOT, model("deepseek-flash"), BOT]

    response = client.post(
        "/matches",
        json={"game": "liars_deck", "seats": seats, "confirm_spend": True, "seed": 3},
    )

    assert response.status_code == 201, response.text
    match = finish(client, response.json()["id"])
    assert match["status"] == "finished"
    kinds = {seat: info["kind"] for seat, info in match["seats"].items()}
    assert kinds == {"p1": "model", "p2": "bot", "p3": "model", "p4": "bot"}
    assert match["seats"]["p2"]["name"] == "Random Bot p2"
    booked = {player for (player,) in rows(database_url, "SELECT DISTINCT player FROM model_calls")}
    assert booked == {"p1", "p3"}
    rated = rows(
        database_url, "SELECT seat FROM match_seats WHERE match_id = $1 ORDER BY seat", match["id"]
    )
    assert rated == [("p1",), ("p3",)]  # the bots are not rated against the models


def test_a_werewolf_village_of_three_models_and_five_bots_plays_to_the_end(client, answer_with):
    answer_with(**NO_TOOL)
    seats = [
        model("glm-flash"),
        BOT,
        BOT,
        model("deepseek-flash"),
        BOT,
        BOT,
        model("qwen-flash"),
        BOT,
    ]

    response = client.post(
        "/matches", json={"game": "werewolf", "seats": seats, "confirm_spend": True, "seed": 2}
    )

    assert response.status_code == 201, response.text
    match = finish(client, response.json()["id"])
    assert match["status"] == "finished"
    assert [info["kind"] for info in match["seats"].values()].count("model") == 3
    assert match["seats"]["p4"]["model_id"] == "deepseek-flash"


def test_a_table_of_bots_named_by_seats_is_a_free_bot_match(client, database_url):
    response = client.post("/matches", json={"game": "toy", "seats": [BOT, BOT, BOT], "seed": 1})

    assert response.status_code == 201, response.text
    match = finish(client, response.json()["id"])
    assert match["players"] == ["p1", "p2", "p3"]
    assert all(info["kind"] == "bot" for info in match["seats"].values())
    assert rows(database_url, "SELECT count(*) FROM model_calls") == [(0,)]


@pytest.mark.parametrize(
    ("body", "status", "says"),
    [
        ({"seats": [model("glm-flash"), BOT]}, 422, "confirm_spend"),
        ({"seats": [BOT, BOT], "models": ["glm-flash", "glm-flash"]}, 422, "not both"),
        ({"seats": [{"kind": "model"}, BOT]}, 422, "names its model"),
        ({"seats": [{"kind": "bot", "model": "glm-flash"}, BOT]}, 422, "names its model"),
        ({"seats": [{**model("glm-flash"), "personality": "bold"}, BOT]}, 422, "not supported yet"),
        ({"seats": [BOT, BOT], "players": 3}, 422, "players is 3"),
        ({"seats": [model("no/such-model"), BOT], "confirm_spend": True}, 422, "Unknown model"),
    ],
)
def test_a_bad_table_is_refused_and_nothing_starts(client, database_url, body, status, says):
    response = client.post("/matches", json={"game": "toy", **body})

    assert response.status_code == status
    assert says in response.text
    assert client.get("/matches").json() == []


def test_model_seats_at_a_mixed_table_still_need_the_server_switch(client, monkeypatch):
    monkeypatch.delenv("ARENA_ALLOW_MODEL_SEATS")

    response = client.post(
        "/matches", json={"game": "toy", "seats": [model("glm-flash"), BOT], "confirm_spend": True}
    )

    assert response.status_code == 403


def test_the_estimate_prices_the_model_seats_and_lets_the_bots_play_for_free(client):
    response = client.post(
        "/matches/estimate", json={"game": "liars_deck", "models": ["glm-flash", None, None]}
    )

    assert response.status_code == 200, response.text
    seats = response.json()["seats"]
    assert set(seats) == {"p1"}
    assert response.json()["estimate_micro_eur"] == seats["p1"]["estimate_micro_eur"] > 0
    only_bots = client.post("/matches/estimate", json={"game": "toy", "models": [None, None]})
    assert only_bots.status_code == 422
