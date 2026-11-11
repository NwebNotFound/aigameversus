"""The spend ledger in a database of its own (LEDGER_DATABASE_URL).

Model seats and costs need the ledger; bot matches do not. LiteLLM answers
from its own mock with every name lookup refused: nothing here costs money.
"""

import asyncio
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from arena.api.app import app
from arena.db.database import connect, migrate
from arena.db.match_store import MatchStore, Seat
from arena.engine.types import Placement
from tests.db.test_cli_models import stored
from tests.db.test_model_seats_api import KEY, MODELS, PLAY_3, calls, finish
from tests.db.test_models_api import play
from tests.test_cli import arena

MODEL_MATCH = {"game": "toy", "models": MODELS, "confirm_spend": True, "seed": 4}


@pytest.fixture
def server(database_url, monkeypatch):
    """Start the API with the ledger at the URL given: `with server(ledger_url) as client`."""
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("ARENA_ALLOW_MODEL_SEATS", "1")
    monkeypatch.setenv("OPENROUTER_API_KEY", KEY)

    def start(ledger_url):
        monkeypatch.setenv("LEDGER_DATABASE_URL", ledger_url)
        return TestClient(app)

    return start


def test_model_calls_are_booked_in_the_ledger_database_and_costs_come_from_there(
    server, database_url, other_database_url, answer_with
):
    answer_with(**PLAY_3)

    with server(other_database_url) as client:
        response = client.post("/matches", json=MODEL_MATCH)
        match = finish(client, response.json()["id"])
        cost = client.get(f"/matches/{match['id']}/cost").json()
        replay = client.get("/replays").json()[0]

    assert match["status"] == "finished"
    booked = calls(other_database_url)
    assert booked and {str(match_id) for match_id, _, _ in booked} == {match["id"]}
    assert calls(database_url) == []
    assert cost["total_micro_eur"] > 0
    assert set(cost["players"]) == {"p1", "p2"}
    assert (replay["id"], replay["cost_micro_eur"]) == (match["id"], cost["total_micro_eur"])


def test_without_its_ledger_the_server_plays_bots_and_refuses_models_and_costs_of_a_match(
    server, closed_port_url, answer_with
):
    sent = answer_with(**PLAY_3)

    with server(closed_port_url) as client:
        bots = finish(client, client.post("/matches", json={"game": "toy"}).json()["id"])
        refused = client.post("/matches", json=MODEL_MATCH)
        cost = client.get(f"/matches/{bots['id']}/cost")
        replays = client.get("/replays")
        listed = client.get("/matches").json()

    assert bots["status"] == "finished"
    assert refused.status_code == 503
    assert "spend ledger cannot be read" in refused.json()["detail"]
    assert [match["id"] for match in listed] == [bots["id"]]
    assert sent == {}
    assert cost.status_code == 503
    assert replays.status_code == 200
    assert [(r["id"], r["cost_micro_eur"]) for r in replays.json()] == [(bots["id"], None)]
    assert KEY not in refused.text


def test_an_empty_ledger_beside_finished_model_matches_is_not_used(
    server, database_url, other_database_url, answer_with
):
    sent = answer_with(**PLAY_3)
    with server(database_url) as client:  # the first match books in the match database
        first = finish(client, client.post("/matches", json=MODEL_MATCH).json()["id"])
    sent.clear()

    with server(other_database_url) as client:  # then the ledger points somewhere empty
        refused = client.post("/matches", json=MODEL_MATCH)
        listed = client.get("/matches").json()

    assert first["status"] == "finished"
    assert refused.status_code == 503
    assert "not the ledger they were booked in" in refused.json()["detail"]
    assert [match["id"] for match in listed] == [first["id"]]
    assert sent == {}
    assert calls(other_database_url) == []


def test_an_imported_model_match_does_not_need_its_calls_in_this_ledger(
    server, database_url, other_database_url, answer_with
):
    answer_with(**PLAY_3)
    asyncio.run(imported_model_match(database_url))

    with server(other_database_url) as client:  # an empty ledger
        started = client.post("/matches", json=MODEL_MATCH)
        match = finish(client, started.json()["id"])

    assert (started.status_code, match["status"]) == (201, "finished")
    assert calls(other_database_url)


async def imported_model_match(database_url):
    """A finished match with model seats, recorded as imported from a file."""
    pool = await connect(database_url)
    try:
        await migrate(pool)
        store, match_id = MatchStore(pool), uuid4()
        seats = {
            seat: Seat(name=model, model_id=model, kind="model")
            for seat, model in zip(["p1", "p2"], MODELS, strict=True)
        }
        await store.create(match_id, "toy", ["p1", "p2"], 1, {}, seats, origin="imported")
        await store.close(match_id, "finished", [Placement(player="p1", rank=1)])
    finally:
        await pool.close()


def test_command_refuses_models_without_its_ledger(
    database_url, closed_port_url, monkeypatch, answer_with, capsys
):
    sent = answer_with(**PLAY_3)
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("LEDGER_DATABASE_URL", closed_port_url)
    monkeypatch.setenv("OPENROUTER_API_KEY", KEY)

    code, output, complaints = arena(
        capsys, "run", "--game", "toy", "--models", "glm-flash,deepseek-flash"
    )

    assert code != 0
    assert "spend ledger cannot be read" in complaints
    assert "Nothing was sent or booked" in complaints
    matches, _, booked = stored(database_url)
    assert (matches, booked, sent) == ([], [], {})


def test_leaderboard_and_model_page_take_their_costs_from_the_ledger_database(
    server, database_url, other_database_url
):
    first = play(database_url, ledger_url=other_database_url)  # glm-flash in p1: 6000
    asyncio.run(book(other_database_url, first, "p2", "deepseek-flash", 4000))

    with server(other_database_url) as client:
        board = {r["model_id"]: r for r in client.get("/leaderboard").json()["rows"]}
        glm = client.get("/models/glm-flash").json()
        deepseek = client.get("/models/deepseek-flash").json()

    # Two seats of one match with different costs: each model gets its own seat's cost.
    assert board["glm-flash"]["cost_per_game_micro_eur"] == 2000  # 6000 over 3 rated games
    assert board["deepseek-flash"]["cost_per_game_micro_eur"] == 1333  # 4000 over 3
    assert glm["usage"]["cost_total_micro_eur"] == 6000
    assert deepseek["usage"]["cost_total_micro_eur"] == 4000
    games = {game["game_id"]: game["usage"] for game in glm["games"]}
    assert games["liars_deck"]["cost_total_micro_eur"] == 6000


async def book(ledger_url, match_id, player, model, cost):
    pool = await connect(ledger_url)
    try:
        await pool.execute(
            "INSERT INTO model_calls (match_id, player, model, called_at, cost_micro_eur) "
            "VALUES ($1, $2, $3, now(), $4)",
            match_id,
            player,
            model,
            cost,
        )
    finally:
        await pool.close()


def test_without_its_ledger_costs_are_unknown_and_the_rest_still_shows(
    server, database_url, closed_port_url
):
    play(database_url)

    with server(closed_port_url) as client:
        board = client.get("/leaderboard")
        page = client.get("/models/glm-flash")

    assert (board.status_code, page.status_code) == (200, 200)
    glm = next(r for r in board.json()["rows"] if r["model_id"] == "glm-flash")
    assert glm["cost_per_game_micro_eur"] is None
    assert glm["tool_error_rate"] == pytest.approx(0.1)
    usage = page.json()["usage"]
    assert (usage["cost_total_micro_eur"], usage["cost_per_game_micro_eur"]) == (None, None)
    assert usage["tool_error_rate"] == pytest.approx(0.1)
