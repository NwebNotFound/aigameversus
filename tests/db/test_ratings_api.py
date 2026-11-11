import asyncio
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from arena.api.app import app
from arena.db.database import connect, migrate
from arena.engine.types import Placement
from arena.ratings.store import RatingStore


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
    assert response.json() == {"game": None, "games": [], "rows": []}


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
    assert body["relations"] == {"available": False, "note": "not available yet"}
    assert body["memory"] == {"available": False, "note": "not available yet"}


def test_unknown_profile_is_404(client):
    response = client.get(f"/profiles/{uuid4()}")

    assert response.status_code == 404


def test_profile_id_must_be_a_uuid(client):
    assert client.get("/profiles/not-a-uuid").status_code == 422


def test_endpoints_are_in_the_openapi_docs(client):
    paths = client.get("/openapi.json").json()["paths"]

    assert "/leaderboard" in paths
    assert "/profiles/{profile_id}" in paths
