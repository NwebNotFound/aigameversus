"""GET /profiles/{id}/stats: a player's statistics, read from the logs of its rated matches."""

import pytest
from fastapi.testclient import TestClient

from arena.api import ratings
from arena.api.app import app
from arena.stats import STATS
from tests.db.test_matches_api import as_events, follow, start


@pytest.fixture
def client(database_url, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", database_url)
    with TestClient(app) as client:
        yield client


def bot(client, game, seat):
    rows = client.get(
        "/leaderboard", params={"game": game, "kind": "all", "group_bots": False}
    ).json()["rows"]
    return next(row["profile_id"] for row in rows if row["name"] == f"Random Bot {seat}")


def play(client, **body):
    match = start(client, **body)
    log, _ = follow(client, match["id"])
    return as_events(log)


def test_stats_of_a_bot_add_up_its_seat_in_every_match(client):
    logs = [play(client, game="liars_deck", seed=seed, players=3) for seed in (5, 6)]
    p2 = bot(client, "liars_deck", "p2")

    stats = client.get(f"/profiles/{p2}/stats").json()

    liars = STATS["liars_deck"]
    expected = liars.aggregate([liars.match_stats(log)["p2"] for log in logs]).model_dump()
    assert stats == {
        "profile_id": p2,
        "games": [{"game_id": "liars_deck", "matches": 2, "stats": expected}],
    }
    assert stats["games"][0]["stats"]["matches"] == 2


def test_stats_are_kept_apart_per_game(client):
    play(client, game="liars_deck", seed=1)
    play(client, game="poker", seed=1, players=3)
    p1 = bot(client, "poker", "p1")

    games = client.get(f"/profiles/{p1}/stats").json()["games"]
    only_poker = client.get(f"/profiles/{p1}/stats", params={"game": "poker"}).json()["games"]

    assert [(g["game_id"], g["matches"]) for g in games] == [("liars_deck", 1), ("poker", 1)]
    assert only_poker == [games[1]]


def test_a_game_the_player_has_not_played_has_no_totals(client):
    play(client, game="poker", seed=2)
    p1 = bot(client, "poker", "p1")

    games = client.get(f"/profiles/{p1}/stats", params={"game": "werewolf"}).json()["games"]

    assert games == [{"game_id": "werewolf", "matches": 0, "stats": None}]


def test_a_game_without_statistics_is_left_out_and_cannot_be_asked_for(client):
    play(client, game="toy", seed=3)
    p1 = bot(client, "toy", "p1")

    assert client.get(f"/profiles/{p1}/stats").json()["games"] == []
    response = client.get(f"/profiles/{p1}/stats", params={"game": "toy"})
    assert response.status_code == 404
    assert response.json()["detail"] == "no statistics for the game 'toy'"


def test_unknown_profile_has_no_stats(client):
    response = client.get("/profiles/00000000-0000-0000-0000-000000000000/stats")

    assert response.status_code == 404


def test_only_the_newest_matches_of_a_game_count(client, monkeypatch):
    logs = [play(client, game="liars_deck", seed=seed) for seed in (7, 8, 9)]
    p1 = bot(client, "liars_deck", "p1")
    monkeypatch.setattr(ratings, "MAX_STATS_MATCHES", 2)

    game = client.get(f"/profiles/{p1}/stats").json()["games"][0]

    liars = STATS["liars_deck"]
    newest = liars.aggregate([liars.match_stats(log)["p1"] for log in logs[1:]])
    assert game["matches"] == 2
    assert game["stats"] == newest.model_dump()
