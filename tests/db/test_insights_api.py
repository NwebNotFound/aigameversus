"""GET /insights: per model across rated matches, with intervals, head-to-head and cost."""

import asyncio
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from arena.api.app import app
from arena.db.database import connect, migrate


@pytest.fixture
def client(database_url, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.delenv("LEDGER_DATABASE_URL", raising=False)
    with TestClient(app) as client:
        yield client


def rated(database_url, game, results, cost_per_seat=0, demo=()):
    """Store rated matches: each a list of model ids in finishing order (first = winner)."""

    async def run():
        pool = await connect(database_url)
        try:
            await migrate(pool)
            profiles = {}
            for models in results:
                for model in models:
                    if model not in profiles:
                        profiles[model] = (
                            await pool.fetchval(
                                "SELECT id FROM player_profiles WHERE model_id = $1", model
                            )
                            or uuid4()
                        )
                        await pool.execute(
                            "INSERT INTO player_profiles (id, name, model_id, is_demo) "
                            "VALUES ($1, $2, $3, $4) ON CONFLICT (id) DO NOTHING",
                            profiles[model],
                            model.upper(),
                            model,
                            model in demo,
                        )
                match_id = uuid4()
                await pool.execute(
                    "INSERT INTO rated_matches (match_id, game_id) VALUES ($1, $2)", match_id, game
                )
                for rank, model in enumerate(models, start=1):
                    seat = f"p{rank}"
                    await pool.execute(
                        "INSERT INTO match_placements (match_id, profile_id, rank, players, "
                        "rating_before, rating_after) VALUES ($1, $2, $3, $4, 1000, 1000)",
                        match_id,
                        profiles[model],
                        rank,
                        len(models),
                    )
                    await pool.execute(
                        "INSERT INTO match_seats (match_id, seat, profile_id) VALUES ($1, $2, $3)",
                        match_id,
                        seat,
                        profiles[model],
                    )
                    if cost_per_seat:
                        await pool.execute(
                            "INSERT INTO model_calls (match_id, player, model, called_at, "
                            "cost_micro_eur) VALUES ($1, $2, $3, $4, $5)",
                            match_id,
                            seat,
                            model,
                            datetime.now(UTC),
                            cost_per_seat,
                        )
        finally:
            await pool.close()

    asyncio.run(run())


def test_insights_rank_nothing_without_rated_matches(client):
    body = client.get("/insights").json()

    assert body["insights_version"] == "insights/1" and body["matches"] == 0
    assert body["models"] == [] and body["head_to_head"] == []
    assert body["min_matches"] == 10


def test_insights_give_win_rates_with_intervals_head_to_head_cost_and_reliability(
    client, database_url
):
    rated(
        database_url,
        "poker",
        [["m-a", "m-b"]] * 7 + [["m-b", "m-a"]] * 3,
        cost_per_seat=1500,
    )
    rated(database_url, "liars_deck", [["m-b", "m-a"]] * 2)

    body = client.get("/insights", params={"game": "poker"}).json()

    assert body["game"] == "poker" and body["matches"] == 10
    a, b = body["models"]
    assert (a["model_id"], a["matches"], a["wins"]) == ("m-a", 10, 7)
    assert a["win_rate"]["value"] == 0.7 and a["win_rate"]["low"] < 0.7 < a["win_rate"]["high"]
    assert not a["provisional"] and a["placement_score"]["value"] == 0.7
    assert a["cost_per_match_micro_eur"] == 1500
    assert a["reliability"]["status"] in ("ok", "unreliable", "unknown")
    (pair,) = body["head_to_head"]
    assert (pair["a"], pair["b"], pair["a_above"], pair["b_above"]) == ("m-a", "m-b", 7, 3)
    assert pair["a_share"]["of"] == 10 and pair["a_share"]["low"] < 0.7
    every = client.get("/insights").json()
    assert every["matches"] == 12  # both games without a filter
    assert client.get("/insights", params={"game": "chess"}).status_code == 404


def test_demo_profiles_stay_out_unless_asked_for(client, database_url):
    rated(database_url, "toy", [["demo-bot", "m-c"]], demo={"demo-bot"})

    shown = {m["model_id"] for m in client.get("/insights").json()["models"]}
    with_demo = {m["model_id"] for m in client.get("/insights?demo=true").json()["models"]}

    assert shown == {"m-c"} and with_demo == {"demo-bot", "m-c"}
