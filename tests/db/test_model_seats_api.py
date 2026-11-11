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
    assert match["seats"]["p3"] == {"name": "Random Bot p3", "model_id": None, "kind": "bot"}
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


def test_a_finished_model_match_is_not_rated(client, database_url, answer_with):
    """Model profiles are not built in the API yet (D-082): no rating, no profile, no memory."""
    answer_with(**PLAY_3)

    response = client.post(
        "/matches", json={"game": "toy", "models": MODELS, "confirm_spend": True}
    )

    match = finish(client, response.json()["id"])
    assert match["status"] == "finished"
    assert set(rated_rows(database_url).values()) == {0}
    assert client.get("/leaderboard").json()["rows"] == []
    bots = finish(client, client.post("/matches", json={"game": "toy"}).json()["id"])
    assert bots["status"] == "finished"
    assert rated_rows(database_url)["rated_matches"] == 1  # a bot match is rated


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


def test_a_model_match_with_memory_on_remembers_nothing_yet(client, database_url, answer_with):
    # Model seats have no profiles yet, so their matches are not rated, and only rated
    # matches are remembered. A bot match of the same game does write a summary.
    answer_with(**PLAY_3)
    models = client.post(
        "/matches",
        json={"game": "toy", "models": MODELS, "confirm_spend": True, "seed": 4, "memory": True},
    ).json()
    bots = client.post("/matches", json={"game": "toy", "seed": 4}).json()
    assert finish(client, models["id"])["status"] == "finished"
    assert finish(client, bots["id"])["status"] == "finished"

    async def remembered():
        pool = await connect(database_url)
        try:
            rows = await pool.fetch("SELECT DISTINCT match_id FROM match_memories")
            return {str(row["match_id"]) for row in rows}
        finally:
            await pool.close()

    assert asyncio.run(remembered()) == {bots["id"]}
