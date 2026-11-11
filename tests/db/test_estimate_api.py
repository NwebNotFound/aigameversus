"""POST /matches/estimate: what a match of models would cost, with no model call."""

import asyncio
import time
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from arena.api import matches
from arena.api.app import app
from arena.db.database import connect, migrate
from tests.db.test_model_seats_api import MODELS, PLAY_3

BODY = {"game": "toy", "models": MODELS}


@pytest.fixture
def client(database_url, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.delenv("ARENA_ALLOW_MODEL_SEATS", raising=False)  # an estimate spends nothing
    monkeypatch.delenv("LEDGER_DATABASE_URL", raising=False)
    with TestClient(app) as client:
        yield client


def booked(database_url, rows):
    """Book calls (model, cost, output tokens) in the ledger, now."""

    async def go():
        pool = await connect(database_url)
        try:
            await migrate(pool)
            for model, cost, output in rows:
                await pool.execute(
                    "INSERT INTO model_calls "
                    "(match_id, player, model, called_at, output_tokens, cost_micro_eur) "
                    "VALUES (gen_random_uuid(), 'p1', $1, $2, $3, $4)",
                    model,
                    datetime.now(UTC),
                    output,
                    cost,
                )
        finally:
            await pool.close()

    asyncio.run(go())


def test_an_estimate_prices_every_seat_and_says_whether_it_fits(client, answer_with):
    sent = answer_with(**PLAY_3)

    response = client.post("/matches/estimate", json=BODY)

    assert response.status_code == 200, response.text
    out = response.json()
    assert set(out["seats"]) == {"p1", "p2"}
    assert [out["seats"][s]["model_id"] for s in ("p1", "p2")] == MODELS
    assert out["estimate_micro_eur"] == sum(s["estimate_micro_eur"] for s in out["seats"].values())
    assert (out["cap_micro_eur"], out["month_cap_micro_eur"]) == (500_000, 25_000_000)
    assert out["month_spent_micro_eur"] == 0
    assert out["fits"] is True
    assert sent == {}  # no model was called
    assert client.get("/matches").json() == []  # and no match was recorded


def test_the_month_so_far_comes_from_the_ledger_and_can_make_it_not_fit(
    client, database_url, answer_with
):
    answer_with(**PLAY_3)
    booked(database_url, [("glm-flash", 24_999_990, 100)])

    out = client.post("/matches/estimate", json=BODY).json()

    assert out["month_spent_micro_eur"] == 24_999_990
    assert out["fits"] is False


def test_history_in_the_ledger_lowers_the_estimate_of_a_model_and_says_so(client, database_url):
    before = client.post("/matches/estimate", json=BODY).json()["seats"]["p1"]
    booked(database_url, [("glm-flash", 1, 50)] * 10)
    client.app.state.estimates.answers.clear()

    after = client.post("/matches/estimate", json=BODY).json()["seats"]["p1"]

    assert before["basis"] == "output limit"
    assert after["basis"] == "ledger history"
    assert after["calls"] == before["calls"]
    assert after["estimate_micro_eur"] < before["estimate_micro_eur"]


def test_the_same_request_within_half_a_minute_gets_the_same_answer(
    client, database_url, monkeypatch
):
    first = client.post("/matches/estimate", json=BODY).json()
    booked(database_url, [("glm-flash", 1, 50)] * 10)  # would change a new estimate
    assert client.post("/matches/estimate", json=BODY).json() == first

    later = matches.ESTIMATE_TTL + 1
    monkeypatch.setattr(matches, "_clock", lambda: time.monotonic() + later)
    assert client.post("/matches/estimate", json=BODY).json() != first


@pytest.mark.parametrize(
    ("body", "status", "detail"),
    [
        ({"game": "chess", "models": MODELS}, 404, "Unknown game"),
        ({"game": "toy", "models": ["glm-flash", "gpt-9"]}, 422, "Unknown model gpt-9"),
        ({"game": "toy", "models": ["glm-flash"]}, 422, "toy needs 2 to 4 players"),
    ],
)
def test_an_estimate_that_cannot_be_made_says_why(client, body, status, detail):
    response = client.post("/matches/estimate", json=body)

    assert response.status_code == status
    assert detail in response.json()["detail"]


def test_without_the_ledger_there_is_no_estimate(database_url, closed_port_url, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("LEDGER_DATABASE_URL", closed_port_url)

    with TestClient(app) as client:
        response = client.post("/matches/estimate", json=BODY)

    assert response.status_code == 503
    assert "spend ledger cannot be read" in response.json()["detail"]
