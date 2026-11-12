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


def test_a_civ_match_has_its_analytics_and_the_spoiler_free_answer_holds_back_private_parts(client):
    match = start(client, game="civ", seed=3, settings={"rounds": 8})
    follow(client, match["id"])

    full = client.get(f"/matches/{match['id']}/analytics", params={"spoilers": True}).json()
    public = client.get(f"/matches/{match['id']}/analytics").json()

    assert full["analytics_version"] == public["analytics_version"] == "civ/1"
    assert full["series"]["rounds"] == list(range(1, 9))
    assert public["series"] is None and public["orders"] is None and public["battles"] is None
    assert full["meta"]["seats"] == {f"p{n}": None for n in range(1, 5)}
    assert full["victory"]["kind"] == public["victory"]["kind"] == "round_limit"
    assert "production" not in json.dumps(public)


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


def test_the_report_adds_duration_and_cost_from_the_record_and_the_ledger(client):
    match = start(client, game="liars_deck", seed=6)
    follow(client, match["id"])

    report = client.get(f"/matches/{match['id']}/analytics").json()["report"]

    glance = report["at_a_glance"]
    assert glance["duration_s"] >= 0 and glance["cost_micro_eur"] == 0  # bots cost nothing
    assert glance["cost_by_seat"] == {"p1": 0, "p2": 0}
    assert all(
        row["values"][-1] == {**report["columns"][-1], "value": 0} for row in report["ranking"]
    )
    assert report["columns"][-1]["key"] == "cost_micro_eur"
    assert glance["winners"] == [report["ranking"][0]["seat"]]


def test_talk_checks_are_served_with_spoilers_and_hold_back_hidden_cards_without(client):
    match = start(client, game="liars_deck", seed=3)
    follow(client, match["id"])

    full = client.get(f"/matches/{match['id']}/talk-checks", params={"spoilers": True}).json()
    public = client.get(f"/matches/{match['id']}/talk-checks").json()

    assert full["game"] == "liars_deck" and full["available"] is True
    assert public["available"] is False and public["tags"] == []


def test_talk_checks_of_unknown_match_or_game_are_404(client):
    toy = start(client, game="toy", seed=1)
    follow(client, toy["id"])

    assert (
        client.get("/matches/00000000-0000-0000-0000-000000000000/talk-checks").status_code == 404
    )
    assert client.get(f"/matches/{toy['id']}/talk-checks").status_code == 404


def test_talk_checks_never_quote_private_werewolf_talk_without_spoilers(client, monkeypatch):
    from arena.engine.types import MESSAGE, Event, EventSource
    from tests.analytics.test_talk import werewolf_log

    match = start(client, game="werewolf", players=8, seed=5)
    follow(client, match["id"])
    secret = "Pack, listen: tomorrow I am the seer and I checked p3, a villager."
    events = [e for _, e in werewolf_log()]
    events.insert(
        5,
        Event(
            source=EventSource.GAME,
            type=MESSAGE,
            data={"player": "p1", "text": secret},
            visible_to=["p1", "p2"],
        ),
    )
    events.append(
        Event(
            source=EventSource.GAME,
            type="player_died",
            data={"player": "p1", "cause": "executed", "role": "werewolf"},
        )
    )

    async def stored(match_id):
        return events

    monkeypatch.setattr(client.app.state.live, "log", stored)

    public = client.get(f"/matches/{match['id']}/talk-checks").json()
    full = client.get(f"/matches/{match['id']}/talk-checks", params={"spoilers": True}).json()

    assert "Pack, listen" not in str(public)
    assert any("Pack, listen" in tag["quote"] for tag in full["tags"])


def test_poker_analytics_has_hands_chips_moves_and_totals_and_no_hidden_cards_in_public(client):
    match = start(client, game="poker", players=3, seed=3)
    follow(client, match["id"])

    full = client.get(f"/matches/{match['id']}/analytics", params={"spoilers": True}).json()
    public = client.get(f"/matches/{match['id']}/analytics").json()

    for answer in (full, public):
        assert {"hands", "chips", "moves", "totals", "report"} <= set(answer["sections"])
        assert answer["players"] == ["p1", "p2", "p3"]
    assert full["totals"]["p1"]["bluff_rate"] is not None or full["totals"]["p1"]["hands"] == 0
    assert (
        public["totals"]["p1"]["bluff_rate"] is None
        and public["totals"]["p1"]["worst_decisions"] is None
    )
    assert public["totals"]["p1"]["vpip"] == full["totals"]["p1"]["vpip"]
    assert "hole_dealt" not in json.dumps(public)
