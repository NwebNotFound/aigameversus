"""GET /matches/{id}/transcript on real stored matches."""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from arena.api.app import app


@pytest.fixture
def client(database_url, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", database_url)
    with TestClient(app) as client:
        yield client


def start(client, game, **body):
    response = client.post("/matches", json={"game": game, **body})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def finish(client, match_id):
    with client.websocket_connect(f"/matches/{match_id}/events") as stream:
        try:
            while True:
                stream.receive_json()
        except WebSocketDisconnect:
            pass


def test_a_match_has_a_transcript_as_json_text_and_markdown(client):
    match_id = start(client, "liars_deck", players=3, seed=5)
    finish(client, match_id)
    url = f"/matches/{match_id}/transcript"

    body = client.get(url, params={"lang": "de"}).json()
    text = client.get(url, params={"format": "text"})
    markdown = client.get(url, params={"format": "markdown"})

    assert (body["game"], body["lang"], body["spoilers"]) == ("liars_deck", "de", False)
    assert body["lines"][0]["kind"] == "heading" and body["lines"][-1]["kind"] == "result"
    assert any(line["text"].startswith("Runde 1, Tischkarte:") for line in body["lines"])
    assert text.headers["content-type"].startswith("text/plain")
    assert "Round 1, table card:" in text.text
    assert markdown.headers["content-type"].startswith("text/markdown")
    assert "\n## Round 1" in markdown.text
    # Every line carries the event it comes from, for the raw toggle.
    assert all(line["raw"]["type"] for line in body["lines"])


def test_spoilers_decide_what_the_transcript_may_tell(client):
    match_id = start(client, "poker", players=3, seed=2)
    finish(client, match_id)
    url = f"/matches/{match_id}/transcript"

    plain = client.get(url, params={"format": "text"}).text
    spoiled = client.get(url, params={"format": "text", "spoilers": True}).text

    assert "is dealt" not in plain and "is dealt" in spoiled
    assert "Showdown:" in plain  # the showdown is public


def test_importance_folds_bookkeeping(client):
    match_id = start(client, "liars_deck", players=3, seed=5)
    finish(client, match_id)
    url = f"/matches/{match_id}/transcript"

    everything = client.get(url, params={"min_importance": 1}).json()["lines"]
    highlights = client.get(url, params={"min_importance": 3}).json()["lines"]

    assert len(highlights) < len(everything)
    assert {line["importance"] for line in highlights} == {3}


def test_players_are_named_after_their_profile_and_model_when_the_match_was_rated(client):
    match_id = start(client, "toy", players=2, seed=3)
    finish(client, match_id)

    text = client.get(f"/matches/{match_id}/transcript", params={"format": "text"}).text

    assert "Random Bot p1" in text and "(random-bot)" not in text


def test_unknown_match_game_and_options_are_refused(client):
    assert client.get(f"/matches/{uuid4()}/transcript").status_code == 404
    match_id = start(client, "toy")
    finish(client, match_id)
    assert client.get(f"/matches/{match_id}/transcript", params={"lang": "fr"}).status_code == 422
    assert (
        client.get(f"/matches/{match_id}/transcript", params={"format": "pdf"}).status_code == 422
    )
    assert (
        client.get(f"/matches/{match_id}/transcript", params={"min_importance": 9}).status_code
        == 422
    )


def test_the_seed_is_not_in_the_json_of_a_transcript_without_spoilers(client):
    match_id = start(client, "liars_deck", players=3, seed=5)
    finish(client, match_id)
    url = f"/matches/{match_id}/transcript"

    plain = client.get(url, params={"spoilers": False}).text
    spoiled = client.get(url, params={"spoilers": True}).text

    assert "seed" not in plain
    assert '"seed"' in spoiled


def test_the_json_names_who_sits_in_each_seat_the_same_with_and_without_spoilers(client):
    match_id = start(client, "liars_deck", players=3, seed=5)
    finish(client, match_id)
    url = f"/matches/{match_id}/transcript"

    plain = client.get(url, params={"spoilers": False}).json()["players"]
    spoiled = client.get(url, params={"spoilers": True}).json()["players"]

    assert list(plain) == ["p1", "p2", "p3"]  # in seat order
    assert plain == spoiled
    # Random bots have no name or model of their own to show.
    assert plain == {seat: {"name": None, "model": None} for seat in ("p1", "p2", "p3")}


def test_a_rated_model_seat_gives_its_name_and_model_as_separate_fields(client):
    import asyncio
    import os
    from uuid import UUID

    from arena.db.database import connect
    from arena.ratings.store import RatingStore

    match_id = start(client, "toy", players=2, seed=3)
    finish(client, match_id)

    async def seat_a_model():
        pool = await connect(os.environ["DATABASE_URL"])
        try:
            store = RatingStore(pool)
            profile = await store.create_profile("Mia", "glm-flash")
            await pool.execute(
                "UPDATE match_seats SET profile_id = $2 WHERE match_id = $1 AND seat = 'p1'",
                UUID(match_id),
                profile,
            )
        finally:
            await pool.close()

    asyncio.run(seat_a_model())
    players = client.get(f"/matches/{match_id}/transcript").json()["players"]

    assert players["p1"] == {"name": "Mia", "model": "glm-flash"}
    assert players["p2"] == {"name": None, "model": None}
