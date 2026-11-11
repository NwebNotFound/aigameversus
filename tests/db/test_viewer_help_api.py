"""GET /games/{id}/viewer-help."""

import pytest
from fastapi.testclient import TestClient

from arena.api.app import app


@pytest.fixture
def client(database_url, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", database_url)
    with TestClient(app) as client:
        yield client


def test_a_game_answers_with_its_rules_and_glossary_in_the_language_asked(client):
    en = client.get("/games/liars_deck/viewer-help").json()
    de = client.get("/games/liars_deck/viewer-help", params={"lang": "de"}).json()

    assert (en["game"], en["lang"], de["lang"]) == ("liars_deck", "en", "de")
    assert (
        en["title"] == "Liar's Deck in 30 seconds" and de["title"] == "Liar's Deck in 30 Sekunden"
    )
    assert 6 <= len(en["lines"]) <= 10 and len(en["lines"]) == len(de["lines"])
    assert {"term", "meaning"} == set(en["glossary"][0])
    assert "Revolver" in {x["term"] for x in en["glossary"]}


def test_every_played_game_of_the_arena_has_help(client):
    for game in client.get("/games").json():
        if game["id"] in ("toy", "civ"):
            continue
        assert client.get(f"/games/{game['id']}/viewer-help").status_code == 200, game["id"]


def test_unknown_game_and_unsupported_language_are_refused(client):
    assert client.get("/games/chess/viewer-help").status_code == 404
    assert client.get("/games/toy/viewer-help").status_code == 404  # a game without help
    assert client.get("/games/poker/viewer-help", params={"lang": "fr"}).status_code == 422
