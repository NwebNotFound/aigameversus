"""Replays: the list of finished matches, and the board at any point of a log."""

import pytest
from fastapi.testclient import TestClient

from arena.api.app import app
from arena.engine.replay import replay
from games.liars_deck.plugin import LiarsDeck
from tests.db.test_match_control_api import book, first_event
from tests.db.test_matches_api import as_events, follow, start


@pytest.fixture
def client(database_url, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", database_url)
    with TestClient(app) as client:
        yield client


def finished(client, **body):
    match = start(client, **body)
    follow(client, match["id"])
    return client.get(f"/matches/{match['id']}").json()


def test_replays_are_the_finished_matches_newest_first(client, database_url):
    older = finished(client, game="toy", seed=1)
    newer = finished(client, game="liars_deck", seed=2, players=3)
    running = start(client, turn_delay=30)
    aborted = start(client, turn_delay=30)
    first_event(client, aborted["id"])
    client.post(f"/matches/{aborted['id']}/abort")
    book(database_url, [(newer["id"], "p1", 120), (newer["id"], "p2", 30)])

    replays = client.get("/replays").json()

    assert [r["id"] for r in replays] == [newer["id"], older["id"]]
    assert running["id"] not in [r["id"] for r in replays]
    top = replays[0]
    assert top == {
        "id": newer["id"],
        "game": "liars_deck",
        "players": ["p1", "p2", "p3"],
        "winners": [p["player"] for p in newer["placements"] if p["rank"] == 1],
        "started_at": newer["started_at"],
        "finished_at": newer["finished_at"],
        "cost_micro_eur": 150,
        "seats": {
            seat: {
                "name": f"Random Bot {seat}",
                "model_id": None,
                "kind": "bot",
                "personality": None,
            }
            for seat in ("p1", "p2", "p3")
        },
        "origin": "played",
        "real": False,
        "prompt_version": "liars_deck-p1",
    }
    assert replays[1]["cost_micro_eur"] == 0
    assert len(top["winners"]) == 1


@pytest.mark.parametrize("cut", [1, 10, 40])
def test_board_after_a_prefix_of_the_log(client, cut):
    match = finished(client, game="liars_deck", seed=5)
    log = client.get(f"/matches/{match['id']}/events").json()

    board = client.get(f"/matches/{match['id']}/board", params={"events": cut}).json()

    plugin = LiarsDeck()
    expected = plugin.render_spec(replay(plugin, as_events(log[:cut])))
    assert board == {"game": "liars_deck", "events": cut, "spec": expected}


def test_board_before_the_first_event_is_empty_and_past_the_end_is_the_whole_log(client):
    match = finished(client, game="liars_deck", seed=5)
    url = f"/matches/{match['id']}/board"

    assert client.get(url, params={"events": 0}).json()["spec"] is None
    assert client.get(url, params={"events": 10_000}).json() == client.get(url).json()
    assert client.get(url, params={"events": -1}).status_code == 422
