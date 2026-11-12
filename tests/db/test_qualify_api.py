"""POST /qualifications: the guards of a paid match, one job at a time, every call in the
ledger under the job's id, no match record. Models are mocks: nothing is spent."""

import asyncio
import time

import asyncpg
import pytest
from fastapi.testclient import TestClient

from arena.agents.mock_llm import HANGS, MockLLM
from arena.agents.model import ModelError
from arena.api import qualify
from arena.api.app import app
from arena.config import load_config
from tests.qualify.test_runner import legal

MODEL = next(iter(load_config().models))
# Four tries per case are reserved (QUALIFY.md: every transport attempt): above EUR 0.01.
NEW = {"model": MODEL, "game": "poker", "confirm_spend": True, "max_eur": 0.1}


@pytest.fixture
def arena(database_url, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("ARENA_ALLOW_MODEL_SEATS", "1")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-not-a-key")
    return database_url


def answering(monkeypatch, make):
    """Every case's call: the job's own metered call, of a mock `make(case)`."""
    monkeypatch.setattr(
        qualify,
        "model_call",
        lambda budget, case, model_id: budget.meter(f"q-{case}", model_id, make(case)),
    )


def finished(client, job_id, seconds=20.0):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        record = client.get(f"/qualifications/{job_id}").json()
        if record["status"] != "running":
            return record
        time.sleep(0.05)
    raise AssertionError("the job did not finish")


def ledger(url, job_id):
    async def read():
        connection = await asyncpg.connect(url)
        try:
            rows = await connection.fetch(
                "SELECT player, cost_micro_eur FROM model_calls WHERE match_id = $1 ORDER BY id",
                job_id,
            )
            return [tuple(row.values()) for row in rows]
        finally:
            await connection.close()

    return asyncio.run(read())


def test_a_job_runs_every_core_case_and_books_each_call_under_its_own_id(arena, monkeypatch):
    answering(monkeypatch, lambda case: legal("poker", case))
    with TestClient(app) as client:
        started = client.post("/qualifications", json=NEW)
        assert started.status_code == 202, started.text
        assert started.json()["status"] == "running"

        record = finished(client, started.json()["id"])

        assert (record["status"], record["badge"], record["reasons"]) == ("qualified", None, [])
        assert record["counts"] == {"clean": 4, "repaired": 0, "failed": 0, "unknown": 0}
        assert [c["case"] for c in record["cases"]] == ["A", "B", "C", "D"]
        assert record["configuration"]["runtime"]["answer_repair"] == "off"
        assert len(record["config_hash"]) == 64 and record["expires_at"]
        assert client.get("/matches").json() == []  # a job is not a match
        calls = ledger(arena, record["id"])
        assert [player for player, _ in calls] == ["q-A", "q-B", "q-C", "q-D"]
        assert sum(cost for _, cost in calls) <= record["reserved_micro_eur"] <= 100_000
        listed = client.get("/qualifications", params={"model": MODEL, "game": "poker"}).json()
        assert [r["id"] for r in listed] == [record["id"]]
        now = client.get("/qualifications/current", params={"model": MODEL, "game": "poker"})
        assert (now.json()["status"], now.json()["last"]["id"]) == ("qualified", record["id"])
        # Another configuration of the same model and game was never tested.
        v1 = client.get(
            "/qualifications/current",
            params={"model": MODEL, "game": "poker", "answer_repair": "v1"},
        ).json()
        assert (v1["status"], v1["reason"]) == (
            "unknown",
            "configuration changed since the last test",
        )


def test_rate_limits_leave_the_job_unknown_and_cost_nothing(arena, monkeypatch):
    answering(monkeypatch, lambda case: MockLLM(ModelError("RateLimitError", retryable=True)))
    with TestClient(app) as client:
        record = finished(client, client.post("/qualifications", json=NEW).json()["id"])

    assert record["status"] == "unknown"
    assert all(reason.endswith("rate limited") for reason in record["reasons"])
    calls = ledger(arena, record["id"])
    assert calls and all(cost == 0 for _, cost in calls)  # a 429 is settled at zero


def test_the_click_cap_holds_in_the_ledger_even_if_the_bound_was_too_low(arena, monkeypatch):
    answering(monkeypatch, lambda case: legal("poker", case))
    monkeypatch.setattr(qualify, "bound_micro_eur", lambda config, model_id, sent: 0)
    with TestClient(app) as client:
        started = client.post("/qualifications", json={**NEW, "max_eur": 0.000001})
        assert started.status_code == 202, started.text
        record = finished(client, started.json()["id"])

    assert record["status"] == "unknown"
    assert record["cases"][0]["reason"] == "budget stop"
    assert ledger(arena, record["id"]) == []  # nothing booked past the cap


@pytest.mark.parametrize(
    ("change", "status", "says"),
    [
        ({"confirm_spend": False}, 422, "confirm_spend"),
        ({"model": "no/such-model"}, 422, "Unknown model"),
        ({"game": "werewolf"}, 422, "no core qualification manifest"),
        ({"game": "toy"}, 422, "no core qualification manifest"),
        ({"game": "chess"}, 404, "Unknown game"),
        ({"max_eur": 0.51}, 422, "per-match cap"),
        ({"max_eur": 0.000001}, 422, "worst case"),  # never shrunk to fit: refused
        ({"answer_repair": "v2"}, 422, ""),
    ],
)
def test_a_job_that_cannot_run_as_asked_is_refused_and_nothing_is_stored(
    arena, change, status, says
):
    with TestClient(app) as client:
        response = client.post("/qualifications", json={**NEW, **change})

        assert response.status_code == status, response.text
        assert says in response.text
        assert client.get("/qualifications").json() == []


def test_qualification_is_off_without_the_model_seat_switch_and_without_a_key(arena, monkeypatch):
    with TestClient(app) as client:
        monkeypatch.delenv("ARENA_ALLOW_MODEL_SEATS")
        assert client.post("/qualifications", json=NEW).status_code == 403
        monkeypatch.setenv("ARENA_ALLOW_MODEL_SEATS", "1")
        monkeypatch.delenv("OPENROUTER_API_KEY")
        assert client.post("/qualifications", json=NEW).status_code == 503
        assert client.get("/qualifications").json() == []
        assert client.get("/qualifications/start").status_code in (404, 422)  # no GET start


def test_one_job_at_a_time_and_a_job_cut_off_by_a_restart_is_unknown(arena, monkeypatch):
    answering(monkeypatch, lambda case: MockLLM(HANGS))
    with TestClient(app) as client:
        first = client.post("/qualifications", json=NEW)
        assert first.status_code == 202
        assert client.post("/qualifications", json=NEW).status_code == 409
    with TestClient(app) as client:  # the arena restarted while it ran
        record = client.get(f"/qualifications/{first.json()['id']}").json()

    assert record["status"] == "unknown"
    assert record["reasons"] == ["interrupted: the arena stopped during the job"]


def test_a_quote_says_what_a_click_would_reserve_and_spends_nothing(arena, monkeypatch):
    answering(monkeypatch, lambda case: legal("poker", case))
    with TestClient(app) as client:
        quote = client.get("/qualifications/quote", params={"model": MODEL, "game": "poker"})
        assert quote.status_code == 200, quote.text
        body = quote.json()
        assert [c["case"] for c in body["cases"]] == ["A", "B", "C", "D"]
        assert body["calls"] == 4 and body["tries_per_call"] == 4
        assert body["default_cap_micro_eur"] == 10_000 and body["max_cap_micro_eur"] == 500_000
        assert body["fits_default"] is (body["reserved_micro_eur"] <= 10_000)
        assert client.get("/qualifications").json() == []  # nothing stored, nothing started

        started = client.post("/qualifications", json=NEW).json()
        assert started["reserved_micro_eur"] == body["reserved_micro_eur"]  # the same bound
        assert started["config_hash"] == body["config_hash"]
        assert (
            client.get(
                "/qualifications/quote", params={"model": MODEL, "game": "werewolf"}
            ).status_code
            == 422
        )
