"""GET /matches/{id}/chronicle on real stored matches."""

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
    """Follow the event stream until the server closes it: the match is over."""
    with client.websocket_connect(f"/matches/{match_id}/events") as stream:
        try:
            while True:
                stream.receive_json()
        except WebSocketDisconnect:
            pass


def test_a_finished_match_has_a_chronicle_as_json_and_as_markdown(client):
    match_id = start(client, "liars_deck", players=3, seed=5)
    finish(client, match_id)

    story = client.get(f"/matches/{match_id}/chronicle", params={"style": "sports", "lang": "de"})
    markdown = client.get(f"/matches/{match_id}/chronicle", params={"format": "markdown"})

    assert story.status_code == 200
    body = story.json()
    assert (body["game"], body["style"], body["lang"]) == ("liars_deck", "sports", "de")
    assert body["chapters"] and all(c["text"] for c in body["chapters"])
    assert markdown.status_code == 200
    assert markdown.headers["content-type"].startswith("text/markdown")
    assert markdown.text.startswith("# The Saga of Liar")


def test_the_same_match_always_tells_the_same_story(client):
    match_id = start(client, "poker", players=3, seed=2)
    finish(client, match_id)

    first = client.get(f"/matches/{match_id}/chronicle").json()
    second = client.get(f"/matches/{match_id}/chronicle").json()

    assert first == second


def test_a_running_match_has_no_chronicle_yet(client):
    match_id = start(client, "liars_deck", players=3, seed=5, turn_delay=2)

    response = client.get(f"/matches/{match_id}/chronicle")

    assert response.status_code == 409
    assert "finished" in response.json()["detail"]
    client.post(f"/matches/{match_id}/abort")


def test_unknown_match_and_unchronicled_game_are_404_and_bad_options_422(client):
    assert client.get(f"/matches/{uuid4()}/chronicle").status_code == 404
    toy = start(client, "toy")
    finish(client, toy)
    assert client.get(f"/matches/{toy}/chronicle").status_code == 404
    assert client.get(f"/matches/{toy}/chronicle", params={"style": "tabloid"}).status_code == 422
    assert client.get(f"/matches/{toy}/chronicle", params={"lang": "fr"}).status_code == 422
