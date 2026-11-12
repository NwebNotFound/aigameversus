"""Model seats through POST /matches: off unless allowed, confirmed, metered, recorded.

LiteLLM answers from its own mock with every name lookup refused (fixtures
`litellm`, `answer_with`): nothing here reaches a provider or costs money.
"""

import asyncio
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from arena.api import live
from arena.api.app import app
from arena.config import load_config
from arena.db.database import connect

CALL = {"id": "call_1", "type": "function"}
PLAY_3 = {
    "mock_response": "A three.",
    "mock_tool_calls": [{**CALL, "function": {"name": "play_card", "arguments": '{"card": 3}'}}],
}
KEY = "THIS-IS-THE-SECRET-KEY"
MODELS = ["glm-flash", "deepseek-flash"]


@pytest.fixture
def client(database_url, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("ARENA_ALLOW_MODEL_SEATS", "1")
    monkeypatch.setenv("OPENROUTER_API_KEY", KEY)
    with TestClient(app) as client:
        yield client


def calls(database_url):
    async def read():
        pool = await connect(database_url)
        try:
            rows = await pool.fetch("SELECT match_id, player, model FROM model_calls ORDER BY id")
            return [tuple(row) for row in rows]
        finally:
            await pool.close()

    return asyncio.run(read())


def finish(client, match_id):
    with client.websocket_connect(f"/matches/{match_id}/events") as stream:
        try:
            while True:
                stream.receive_json()
        except Exception:
            pass
    return client.get(f"/matches/{match_id}").json()


def test_models_play_a_match_that_is_metered_and_says_who_sat_where(
    client, database_url, answer_with
):
    sent = answer_with(**PLAY_3)
    config = load_config()

    response = client.post(
        "/matches", json={"game": "toy", "models": MODELS, "confirm_spend": True, "seed": 4}
    )

    assert response.status_code == 201, response.text
    match = finish(client, response.json()["id"])
    assert match["status"] == "finished"
    assert match["players"] == ["p1", "p2"]
    assert match["origin"] == "played"
    assert match["seats"] == {
        f"p{n}": {
            "name": config.models[model].name or model,
            "model_id": model,
            "kind": "model",
            "personality": None,  # none chosen
        }
        for n, model in enumerate(MODELS, start=1)
    }
    assert sent["model"].startswith("openrouter/")
    booked = calls(database_url)
    assert {(player, model) for _, player, model in booked} == {
        ("p1", MODELS[0]),
        ("p2", MODELS[1]),
    }
    assert all(str(match_id) == match["id"] for match_id, _, _ in booked)
    replay = client.get("/replays").json()[0]
    assert (replay["id"], replay["real"]) == (match["id"], True)


def test_the_transcript_names_the_models_of_a_running_match_and_after_it(client, answer_with):
    answer_with(**PLAY_3)
    config = load_config()
    response = client.post(
        "/matches",
        json={"game": "toy", "models": MODELS, "confirm_spend": True, "seed": 4, "turn_delay": 5},
    )
    match_id = response.json()["id"]

    def players():
        return client.get(f"/matches/{match_id}/transcript").json()["players"]

    expected = {
        f"p{n}": {
            "seat": f"p{n}",
            "display": model,
            "name": config.models[model].name or model,
            "model": model,
            "kind": "model",
            "vendor": config.models[model].model.split("/")[0],
        }
        for n, model in enumerate(MODELS, start=1)
    }
    running = players()  # the match is still running: nobody has rated it yet
    client.post(f"/matches/{match_id}/abort")
    finish(client, match_id)

    assert client.get(f"/matches/{match_id}").json()["status"] == "aborted"
    assert running == expected
    assert players() == expected
    text = client.get(f"/matches/{match_id}/transcript", params={"format": "text"}).text
    assert "glm-flash" in text and "deepseek-flash" in text
    assert "Bot " not in text and "p1" not in text


def test_cap_ends_a_model_match_as_interrupted_before_any_call(
    client, database_url, answer_with, monkeypatch
):
    sent = answer_with(**PLAY_3)
    config = load_config()
    tight = config.limits.model_copy(update={"match_eur": Decimal("0.000001")})
    monkeypatch.setattr(live, "load_config", lambda: config.model_copy(update={"limits": tight}))

    response = client.post(
        "/matches", json={"game": "toy", "models": MODELS, "confirm_spend": True}
    )

    match = finish(client, response.json()["id"])
    assert match["status"] == "interrupted"
    assert sent == {}
    assert calls(database_url) == []


@pytest.mark.parametrize(
    ("body", "status", "detail"),
    [
        ({"models": MODELS}, 422, "send confirm_spend: true"),
        ({"models": MODELS, "confirm_spend": True, "players": 3}, 422, "one per seat"),
        ({"models": ["glm-flash", "gpt-9"], "confirm_spend": True}, 422, "Unknown model gpt-9"),
        ({"models": ["glm-flash"], "confirm_spend": True}, 422, "toy needs 2 to 4 players"),
    ],
)
def test_model_match_that_cannot_start_is_refused_and_nothing_runs(
    client, database_url, answer_with, body, status, detail
):
    sent = answer_with(**PLAY_3)

    response = client.post("/matches", json={"game": "toy", **body})

    assert response.status_code == status
    assert detail in response.json()["detail"]
    assert client.get("/matches").json() == []
    assert (sent, calls(database_url)) == ({}, [])


def test_model_seats_are_off_unless_the_server_allows_them(client, answer_with, monkeypatch):
    sent = answer_with(**PLAY_3)
    monkeypatch.delenv("ARENA_ALLOW_MODEL_SEATS")

    response = client.post(
        "/matches", json={"game": "toy", "models": MODELS, "confirm_spend": True}
    )

    assert response.status_code == 403
    assert "ARENA_ALLOW_MODEL_SEATS=1" in response.json()["detail"]
    assert client.get("/matches").json() == []
    assert sent == {}


def test_model_seats_need_the_provider_key_and_never_show_it(client, answer_with, monkeypatch):
    sent = answer_with(**PLAY_3)
    monkeypatch.setenv("OPENROUTER_API_KEY", "")

    response = client.post(
        "/matches", json={"game": "toy", "models": MODELS, "confirm_spend": True}
    )

    assert response.status_code == 503
    assert "OPENROUTER_API_KEY" in response.json()["detail"]
    assert client.get("/matches").json() == []
    assert sent == {}


def test_bot_match_names_its_seats_as_random_bots(client):
    response = client.post("/matches", json={"game": "toy", "players": 3})

    match = finish(client, response.json()["id"])
    assert match["seats"]["p3"] == {
        "name": "Random Bot p3",
        "model_id": None,
        "kind": "bot",
        "personality": None,
    }
    assert match["prompt_version"] == "v1"
    assert KEY not in response.text


def rated_rows(database_url):
    """Rows of every table that rating and memory write, per table."""
    tables = (
        "player_profiles",
        "ratings",
        "rated_matches",
        "match_seats",
        "relationships",
        "remembered_matches",
    )

    async def read():
        pool = await connect(database_url)
        try:
            return {table: await pool.fetchval(f"SELECT count(*) FROM {table}") for table in tables}
        finally:
            await pool.close()

    return asyncio.run(read())


def test_a_finished_model_match_is_rated_with_one_profile_per_model(
    client, database_url, answer_with
):
    """D-081: model matches are rated, one profile per model, the same in every match."""
    answer_with(**PLAY_3)
    body = {"game": "toy", "models": MODELS, "confirm_spend": True}

    for seed in (4, 5):
        response = client.post("/matches", json={**body, "seed": seed})
        assert finish(client, response.json()["id"])["status"] == "finished"

    rows = rated_rows(database_url)
    assert (rows["player_profiles"], rows["rated_matches"], rows["match_seats"]) == (2, 2, 4)
    board = client.get("/leaderboard", params={"kind": "models"}).json()["rows"]
    assert sorted(row["name"] for row in board) == sorted(MODELS)
    assert {row["games_played"] for row in board} == {2}
    bots = finish(client, client.post("/matches", json={"game": "toy"}).json()["id"])
    assert bots["status"] == "finished"
    assert rated_rows(database_url)["rated_matches"] == 3  # the bot match is rated too


def test_a_model_in_two_seats_leaves_the_match_unrated_and_the_match_finishes(
    client, database_url, answer_with
):
    answer_with(**PLAY_3)

    response = client.post(
        "/matches",
        json={"game": "toy", "models": ["glm-flash", "glm-flash"], "confirm_spend": True},
    )

    assert finish(client, response.json()["id"])["status"] == "finished"
    assert set(rated_rows(database_url).values()) == {0}


def test_a_rating_error_never_fails_a_model_match(client, answer_with, monkeypatch):
    from arena.ratings.store import RatingStore

    answer_with(**PLAY_3)

    async def broken(*args, **kwargs):
        raise RuntimeError("the database is gone")

    monkeypatch.setattr(RatingStore, "rate_model_match", broken)
    response = client.post(
        "/matches", json={"game": "toy", "models": MODELS, "confirm_spend": True}
    )

    assert finish(client, response.json()["id"])["status"] == "finished"


def test_the_backfill_rates_the_model_matches_played_before_and_only_once(
    client, database_url, answer_with, monkeypatch, capsys
):
    from arena import cli
    from arena.ratings.store import RatingStore

    answer_with(**PLAY_3)
    real = RatingStore.rate_model_match

    async def not_yet(*args, **kwargs):
        return "not rated in those days"

    monkeypatch.setattr(RatingStore, "rate_model_match", not_yet)
    ended = {}
    for seed in (4, 5):
        started = client.post(
            "/matches", json={"game": "toy", "models": MODELS, "confirm_spend": True, "seed": seed}
        )
        match = finish(client, started.json()["id"])
        assert match["status"] == "finished"
        ended[match["id"]] = match["finished_at"]
    assert client.get("/leaderboard", params={"kind": "models"}).json()["rows"] == []
    monkeypatch.setattr(RatingStore, "rate_model_match", real)

    first = cli.main(["ratings", "backfill"])
    assert (first, capsys.readouterr().out) == (0, "Rated 2 model match(es).\n")
    again = cli.main(["ratings", "backfill"])

    assert (again, capsys.readouterr().out) == (0, "Rated 0 model match(es).\n")
    board = client.get("/leaderboard", params={"kind": "models"}).json()["rows"]
    assert sorted(row["name"] for row in board) == sorted(MODELS)
    assert {row["games_played"] for row in board} == {2}
    # The model page dates a backfilled match by when it ended, not by when it was rated.
    recent = client.get("/models/glm-flash").json()["recent_matches"]
    assert {m["match_id"]: m["played_at"] for m in recent} == ended
    assert all(m["played_at"] < m["rated_at"] for m in recent)


def test_key_is_read_from_its_file_at_every_start(client, answer_with, monkeypatch, tmp_path):
    answer_with(**PLAY_3)
    key_file = tmp_path / "openrouter_api_key"
    monkeypatch.setenv("OPENROUTER_API_KEY", "")
    monkeypatch.setenv("OPENROUTER_API_KEY_FILE", str(key_file))
    body = {"game": "toy", "models": MODELS, "confirm_spend": True}

    key_file.write_text(KEY + "\n", encoding="utf-8")
    started = client.post("/matches", json=body)
    played = finish(client, started.json()["id"])
    key_file.write_text("", encoding="utf-8")  # emptied: the key read before no longer counts
    refused = client.post("/matches", json=body)

    assert (started.status_code, played["status"]) == (201, "finished")
    assert refused.status_code == 503
    assert "OPENROUTER_API_KEY" in refused.json()["detail"]
    assert KEY not in started.text + refused.text


def test_model_seats_get_the_prompt_version_of_the_settings(client, answer_with):
    sent = answer_with(
        mock_response="Check.",
        mock_tool_calls=[{**CALL, "function": {"name": "check", "arguments": "{}"}}],
    )
    settings = {"prompt_version": "poker-p2", "hand_limit": 1}

    response = client.post(
        "/matches",
        json={"game": "poker", "models": MODELS, "confirm_spend": True, "settings": settings},
    )

    match = finish(client, response.json()["id"])
    assert match["status"] == "finished"
    started = client.get(f"/matches/{match['id']}/events").json()[0]
    assert started["data"]["prompt_version"] == "poker-p2"
    assert match["prompt_version"] == "poker-p2"
    assert client.get("/replays").json()[0]["prompt_version"] == "poker-p2"
    assert sent["messages"][1]["content"].startswith("<summary>\nYou are p")


def test_a_model_match_with_memory_on_is_remembered_like_a_bot_match(
    client, database_url, answer_with
):
    answer_with(**PLAY_3)
    models = client.post(
        "/matches",
        json={"game": "toy", "models": MODELS, "confirm_spend": True, "seed": 4, "memory": True},
    ).json()
    quiet = client.post(
        "/matches",
        json={"game": "toy", "models": MODELS, "confirm_spend": True, "seed": 5, "memory": False},
    ).json()
    assert finish(client, models["id"])["status"] == "finished"
    assert finish(client, quiet["id"])["status"] == "finished"

    async def remembered():
        pool = await connect(database_url)
        try:
            rows = await pool.fetch("SELECT DISTINCT match_id FROM match_memories")
            return {str(row["match_id"]) for row in rows}
        finally:
            await pool.close()

    assert asyncio.run(remembered()) == {models["id"]}  # rated, and memory on; the other off


def test_every_model_move_of_an_api_match_is_timed(client, database_url, answer_with):
    answer_with(**PLAY_3)

    response = client.post(
        "/matches", json={"game": "toy", "models": MODELS, "confirm_spend": True, "seed": 4}
    )

    match = finish(client, response.json()["id"])
    events = client.get(f"/matches/{match['id']}/events").json()
    moves = [e for e in events if e["type"] == "decision"]
    assert moves and all(isinstance(m["data"]["latency_ms"], int) for m in moves)
    assert all(m["visible_to"] == [] for m in moves)


def test_a_matchs_own_spend_limit_stops_it_before_a_call_passes_it(
    client, database_url, answer_with
):
    answer_with(**PLAY_3)
    tiny = 0.000001  # one millionth of a euro: no call fits under it

    response = client.post(
        "/matches",
        json={
            "game": "toy",
            "models": MODELS,
            "confirm_spend": True,
            "seed": 4,
            "settings": {"match_budget_eur": tiny},
        },
    )

    assert response.status_code == 201, response.text
    match = finish(client, response.json()["id"])
    assert match["status"] == "interrupted"  # the cap of this match ended it
    assert match["settings"]["match_budget_eur"] == tiny  # recorded with the match
    assert calls(database_url) == []  # nothing was booked, nothing was sent
    started = client.get(f"/matches/{match['id']}/events").json()[0]
    assert started["data"]["settings"]["match_budget_eur"] == tiny


@pytest.mark.parametrize("value", [0, -1, 0.51, "0.2", True])
def test_a_spend_limit_outside_zero_to_the_cap_is_refused(client, value):
    response = client.post(
        "/matches",
        json={
            "game": "toy",
            "models": MODELS,
            "confirm_spend": True,
            "settings": {"match_budget_eur": value},
        },
    )

    assert response.status_code == 422
    assert "match_budget_eur" in response.text
    assert client.get("/matches").json() == []
