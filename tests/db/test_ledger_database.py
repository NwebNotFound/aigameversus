"""The spend ledger in a database of its own (LEDGER_DATABASE_URL).

Model seats and costs need the ledger; bot matches do not. LiteLLM answers
from its own mock with every name lookup refused: nothing here costs money.
"""

import socket

import pytest
from fastapi.testclient import TestClient

from arena.api.app import app
from tests.db.test_cli_models import stored
from tests.db.test_model_seats_api import KEY, MODELS, PLAY_3, calls, finish
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


@pytest.fixture
def closed_port_url():
    """A Postgres URL on a local port where nothing listens."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    return f"postgresql://arena:arena@127.0.0.1:{port}/arena"


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


def test_without_its_ledger_the_server_plays_bots_and_refuses_models_and_costs(
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
    assert (cost.status_code, replays.status_code) == (503, 503)
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
