"""GET /matches/{id}/analytics on bot matches through the API."""

import json

import pytest
from fastapi.testclient import TestClient

from arena.api.app import app
from tests.db.test_matches_api import follow, start


@pytest.fixture
def client(database_url, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", database_url)
    with TestClient(app) as client:
        yield client


def test_a_finished_match_has_its_analytics_with_and_without_spoilers(client):
    match = start(client, game="liars_deck", seed=3)
    follow(client, match["id"])

    full = client.get(f"/matches/{match['id']}/analytics", params={"spoilers": True}).json()
    public = client.get(f"/matches/{match['id']}/analytics").json()

    assert (full["game"], full["spoilers"], public["spoilers"]) == ("liars_deck", True, False)
    assert full["players"] == public["players"] == ["p1", "p2"]
    assert sum(t["plays_known"] for t in full["totals"].values()) == sum(
        t["plays"] for t in full["totals"].values()
    )
    assert public["events"] < full["events"]
    assert public["meta"]["seed"] is None and full["meta"]["seed"] == 3
    assert full["meta"]["seats"] == public["meta"]["seats"] == {"p1": None, "p2": None}
    assert "cards_hidden" not in json.dumps(public)


def test_a_running_match_answers_with_its_turns_so_far(client):
    match = start(client, game="liars_deck", seed=4, turn_delay=30)
    with client.websocket_connect(f"/matches/{match['id']}/events") as stream:
        stream.receive_json()
        answer = client.get(f"/matches/{match['id']}/analytics", params={"spoilers": True})

    assert answer.status_code == 200
    assert answer.json()["players"] == ["p1", "p2"]


def test_unknown_match_and_game_without_analytics_are_404(client):
    toy = start(client, game="toy", seed=1)
    follow(client, toy["id"])

    assert client.get("/matches/00000000-0000-0000-0000-000000000000/analytics").status_code == 404
    missing = client.get(f"/matches/{toy['id']}/analytics")
    assert missing.status_code == 404
    assert "No analytics for toy yet" in missing.json()["detail"]


def test_every_game_with_a_situation_says_how_it_is_going_by_display_name(client):
    for game, players in (("liars_deck", 3), ("poker", 3), ("werewolf", 8)):
        match = start(client, game=game, players=players, seed=5)
        follow(client, match["id"])

        answer = client.get(f"/matches/{match['id']}/analytics")

        assert answer.status_code == 200, game
        lines = answer.json()["situation"]["lines"]
        assert lines["en"] and lines["de"]
        text = " ".join(lines["en"] + lines["de"])
        assert "p1" not in text and "p2" not in text, text
        assert answer.json()["meta"]["seats"]["p1"] is None
        if game == "werewolf":
            recap = answer.json()["recap"]
            assert recap and all("p1" not in r["text"]["en"] for r in recap)
