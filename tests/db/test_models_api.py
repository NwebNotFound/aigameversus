"""GET /models/{id}: one model across its matches and seats."""

import asyncio
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from arena.api.app import app
from arena.db.database import connect, migrate
from arena.engine.types import Placement
from arena.ratings.store import RatingStore


@pytest.fixture
def client(database_url, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", database_url)
    with TestClient(app) as client:
        yield client


def play(database_url, ledger_url=None):
    """Two matches of Liar's Deck and one of Poker between glm-flash and deepseek-flash.

    glm-flash sits in seat p1, then in p2; it wins the first Liar's Deck match. Its calls cost
    6000 in the first match (booked in `ledger_url`, default the match database) and its
    engine log has 9 accepted answers and 1 refused one. Returns the id of that first match.
    """

    async def go():
        pool = await connect(database_url)
        try:
            await migrate(pool)
            store = RatingStore(pool)
            glm = await store.model_profile("glm-flash")
            deepseek = await store.model_profile("deepseek-flash")
            await store.model_profile("glm-flash", "silent_observer")
            first = uuid4()
            for match_id, game, seats, winner in (
                (first, "liars_deck", {"p1": glm, "p2": deepseek}, glm),
                (uuid4(), "liars_deck", {"p1": deepseek, "p2": glm}, deepseek),
                (uuid4(), "poker", {"p1": glm, "p2": deepseek}, glm),
            ):
                placements = [
                    Placement(player=str(p), rank=1 if p == winner else 2) for p in seats.values()
                ]
                await store.apply_match_result(match_id, game, placements, seats=seats)
            ledger = await connect(ledger_url) if ledger_url else pool
            try:
                await migrate(ledger)
                await ledger.execute(
                    "INSERT INTO model_calls (match_id, player, model, called_at, cost_micro_eur) "
                    "VALUES ($1, 'p1', 'glm-flash', now(), 6000)",
                    first,
                )
            finally:
                if ledger is not pool:
                    await ledger.close()
            answers = ["action_accepted"] * 9 + ["action_rejected"]
            for seq, kind in enumerate(answers):
                await pool.execute(
                    "INSERT INTO match_events (match_id, seq, source, type, data, visible_to) "
                    "VALUES ($1, $2, 'engine', $3, $4, '{}')",
                    first,
                    seq,
                    kind,
                    {"player": "p1"},
                )
            return first
        finally:
            await pool.close()

    return asyncio.run(go())


def test_a_model_page_has_rating_cost_and_tool_errors_per_game_and_overall(database_url, client):
    play(database_url)

    page = client.get("/models/glm-flash").json()

    assert page["model"]["id"] == "glm-flash"
    assert page["model"]["vendor"] == "z-ai"
    assert page["model"]["provider_model"].startswith("z-ai/")
    assert page["profile_id"] is not None
    games = {g["game_id"]: g for g in page["games"]}
    assert set(games) == {"liars_deck", "poker"}
    assert games["liars_deck"]["games_played"] == 2 and games["liars_deck"]["win_rate"] == 0.5
    assert games["poker"]["win_rate"] == 1.0
    # The cost and the answers were booked in one Liar's Deck match.
    assert games["liars_deck"]["usage"]["cost_total_micro_eur"] == 6000
    assert games["liars_deck"]["usage"]["cost_per_game_micro_eur"] == 3000
    assert games["liars_deck"]["usage"]["tool_error_rate"] == pytest.approx(0.1)
    assert games["poker"]["usage"]["tool_error_rate"] is None
    assert page["usage"]["cost_total_micro_eur"] == 6000
    assert page["usage"]["cost_per_game_micro_eur"] == 2000  # over its 3 rated games
    assert page["overall"]["games_played"] == 3
    assert len(page["recent_matches"]) == 3
    assert [p["personality_id"] for p in page["personalities"]] == ["silent_observer"]


def test_it_is_the_same_page_whichever_seat_the_model_sat_in(database_url, client):
    play(database_url)

    rows = client.get("/leaderboard", params={"kind": "models"}).json()["rows"]

    assert sorted(r["name"] for r in rows) == ["deepseek-flash", "glm-flash"]
    glm = next(r for r in rows if r["name"] == "glm-flash")
    assert glm["games_played"] == 3  # p1 and p2 seats together


def test_a_configured_model_that_has_not_played_gives_an_empty_page(client):
    page = client.get("/models/qwen-flash").json()

    assert page["model"]["id"] == "qwen-flash" and page["profile_id"] is None
    assert (page["games"], page["overall"], page["recent_matches"]) == ([], None, [])
    assert page["usage"]["tool_error_rate"] is None


def test_an_unknown_model_is_404(client):
    assert client.get("/models/no-such-model").status_code == 404
