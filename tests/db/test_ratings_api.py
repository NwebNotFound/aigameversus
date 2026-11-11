import asyncio
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from arena.api.app import app
from arena.api.ratings import group_seat_bots
from arena.db.database import connect, migrate
from arena.engine.types import Placement
from arena.ratings.store import BOT_MODEL_ID, RatingStore, Standing, Usage


def seed(database_url, matches):
    """Create profiles p0..pN and apply `matches` [(game, [rank per profile])]; return ids."""

    async def go():
        pool = await connect(database_url)
        try:
            await migrate(pool)
            store = RatingStore(pool)
            count = max(len(ranks) for _, ranks in matches)
            ids = [str(await store.create_profile(f"p{i}", f"model-{i}")) for i in range(count)]
            for game, ranks in matches:
                placements = [Placement(player=ids[i], rank=r) for i, r in enumerate(ranks)]
                await store.apply_match_result(uuid4(), game, placements)
            return ids
        finally:
            await pool.close()

    return asyncio.run(go())


@pytest.fixture
def client(database_url, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", database_url)
    with TestClient(app) as client:
        yield client


def test_empty_leaderboard(client):
    response = client.get("/leaderboard")

    assert response.status_code == 200
    assert response.json() == {
        "game": None,
        "games": [],
        "kind": "all",
        "fallback": True,
        "counts": {"models": 0, "bots": 0},
        "rows": [],
    }


def test_leaderboard_per_game(database_url, client):
    ids = seed(database_url, [("poker", [1, 2]), ("poker", [1, 2]), ("werewolf", [2, 1])])

    body = client.get("/leaderboard", params={"game": "poker"}).json()

    assert body["game"] == "poker"
    assert body["games"] == ["poker", "werewolf"]
    first, second = body["rows"]
    assert first == {
        "rank": 1,
        "profile_id": ids[0],
        "name": "p0",
        "model_id": "model-0",
        "rating": first["rating"],
        "games_played": 2,
        "win_rate": 1.0,
        "average_placement": 1.0,
        "kind": "model",
        "vendor": None,  # "model-0" is not in config/models.yaml
        "members": 1,
        "cost_per_game_micro_eur": None,
        "tool_error_rate": None,
    }
    assert first["rating"] > 1000 > second["rating"]
    assert second["rank"] == 2 and second["win_rate"] == 0.0


def test_overall_leaderboard(database_url, client):
    seed(database_url, [("poker", [1, 2]), ("werewolf", [1, 2])])

    rows = client.get("/leaderboard").json()["rows"]

    assert [(r["name"], r["games_played"]) for r in rows] == [("p0", 2), ("p1", 2)]
    assert rows[0]["rating"] == 1016.0


def test_unknown_game_has_no_rows(database_url, client):
    seed(database_url, [("poker", [1, 2])])

    body = client.get("/leaderboard", params={"game": "chess"}).json()

    assert body["rows"] == []
    assert body["games"] == ["poker"]


def test_profile(database_url, client):
    ids = seed(database_url, [("poker", [1, 2]), ("werewolf", [2, 1])])

    body = client.get(f"/profiles/{ids[0]}").json()

    assert body["name"] == "p0"
    assert body["overall"]["games_played"] == 2
    assert body["overall"]["win_rate"] == 0.5
    assert [r["game_id"] for r in body["ratings"]] == ["poker", "werewolf"]
    assert [m["game_id"] for m in body["recent_matches"]] == ["werewolf", "poker"]
    assert body["recent_matches"][1]["rating_change"] == 16.0
    assert "relations" not in body  # GET /profiles/{id}/relations
    assert "memory" not in body  # GET /profiles/{id}/memories


def test_unknown_profile_is_404(client):
    response = client.get(f"/profiles/{uuid4()}")

    assert response.status_code == 404


def test_profile_id_must_be_a_uuid(client):
    assert client.get("/profiles/not-a-uuid").status_code == 422


def test_endpoints_are_in_the_openapi_docs(client):
    paths = client.get("/openapi.json").json()["paths"]

    assert "/leaderboard" in paths
    assert "/profiles/{profile_id}" in paths


def add_usage(database_url, profile_id, game, *, cost, accepted, rejected):
    """Put a rated match of one seat into the database with its booked cost and answers."""

    async def go():
        pool = await connect(database_url)
        try:
            match_id = uuid4()
            await pool.execute(
                "INSERT INTO rated_matches (match_id, game_id) VALUES ($1, $2)", match_id, game
            )
            await pool.execute(
                "INSERT INTO match_seats (match_id, seat, profile_id) VALUES ($1, 'p1', $2)",
                match_id,
                profile_id,
            )
            await pool.execute(
                "INSERT INTO model_calls (match_id, player, model, called_at, cost_micro_eur) "
                "VALUES ($1, 'p1', 'x', now(), $2)",
                match_id,
                cost,
            )
            events = [("action_accepted", "p1")] * accepted + [("action_rejected", "p1")] * rejected
            events += [("action_accepted", "p2")]  # another seat's answer is not counted
            for seq, (kind, player) in enumerate(events):
                await pool.execute(
                    "INSERT INTO match_events (match_id, seq, source, type, data, visible_to) "
                    "VALUES ($1, $2, 'engine', $3, $4, '{}')",
                    match_id,
                    seq,
                    kind,
                    {"player": player},
                )
        finally:
            await pool.close()

    asyncio.run(go())


def test_the_board_shows_cost_per_game_and_the_share_of_refused_answers(database_url, client):
    ids = seed(database_url, [("poker", [1, 2]), ("poker", [2, 1])])
    add_usage(database_url, ids[0], "poker", cost=6000, accepted=9, rejected=1)

    rows = {
        r["name"]: r for r in client.get("/leaderboard", params={"game": "poker"}).json()["rows"]
    }

    assert rows["p0"]["tool_error_rate"] == pytest.approx(0.1)
    assert rows["p0"]["cost_per_game_micro_eur"] == 3000  # 6000 over its 2 rated games
    assert rows["p1"]["cost_per_game_micro_eur"] is None and rows["p1"]["tool_error_rate"] is None


def test_real_models_are_the_default_and_bots_are_one_grouped_row(database_url, client):
    ids = seed(database_url, [("poker", [1, 2])])

    async def bots():
        pool = await connect(database_url)
        try:
            store = RatingStore(pool)
            profiles = await store.bot_profiles(["p1", "p2", "p3"])
            for rank_a, rank_b in ((1, 2), (2, 3), (3, 1)):
                match = [profiles["p1"], profiles["p2"], profiles["p3"]]
                placements = [
                    Placement(player=str(match[0]), rank=rank_a),
                    Placement(player=str(match[1]), rank=rank_b),
                    Placement(player=str(match[2]), rank=1 if rank_a != 1 and rank_b != 1 else 3),
                ]
                await store.apply_match_result(uuid4(), "poker", placements)
        finally:
            await pool.close()

    asyncio.run(bots())

    default = client.get("/leaderboard", params={"game": "poker"}).json()
    everyone = client.get("/leaderboard", params={"game": "poker", "kind": "all"}).json()
    bots = client.get("/leaderboard", params={"game": "poker", "kind": "bots"}).json()

    assert (default["kind"], default["fallback"]) == ("models", False)
    assert [r["name"] for r in default["rows"]] == ["p0", "p1"]
    assert default["counts"] == {"models": 2, "bots": 1}
    assert [r["name"] for r in bots["rows"]] == ["Random Bot"]
    assert (bots["rows"][0]["members"], bots["rows"][0]["games_played"]) == (3, 9)
    assert bots["rows"][0]["kind"] == "bot"
    assert {r["name"] for r in everyone["rows"]} == {"p0", "p1", "Random Bot"}
    assert ids  # the model profiles exist


def test_without_any_rated_model_the_default_falls_back_to_everyone(database_url, client):
    async def bots():
        pool = await connect(database_url)
        try:
            await migrate(pool)
            store = RatingStore(pool)
            profiles = await store.bot_profiles(["p1", "p2"])
            placements = [
                Placement(player=str(profiles["p1"]), rank=1),
                Placement(player=str(profiles["p2"]), rank=2),
            ]
            await store.apply_match_result(uuid4(), "toy", placements)
        finally:
            await pool.close()

    asyncio.run(bots())

    body = client.get("/leaderboard").json()
    models = client.get("/leaderboard", params={"kind": "models"}).json()

    assert (body["kind"], body["fallback"]) == ("all", True)
    assert [r["name"] for r in body["rows"]] == ["Random Bot"]
    assert (models["kind"], models["fallback"], models["rows"]) == ("models", False, [])


def test_grouped_bots_cost_is_unknown_when_a_seat_cost_is_unknown():
    seats = [
        Standing(uuid4(), f"Random Bot p{n}", BOT_MODEL_ID, 1000.0, 1, None, None) for n in (1, 2)
    ]
    usage = {seats[0].profile_id: Usage(None, 3, 1), seats[1].profile_id: Usage(None, 1, 0)}

    (grouped, members), rest = group_seat_bots(seats, usage)

    assert (members, rest) == (2, [])
    assert usage[grouped.profile_id] == Usage(None, 4, 1)
