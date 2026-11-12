"""Jev's calls count against the match's caps like model calls. Jev is a fake: nothing is spent."""

import pytest
from fastapi.testclient import TestClient

from arena.api.app import app
from arena.engine.types import MatchPaused
from arena.jev.client import ALLOW_JEV, FakeJev, JevError
from arena.jev.config import load_jev_config
from tests.db.test_budget import NOVEMBER, booked, budget_of, with_pool

JEV = load_jev_config()
QUESTIONS = {"q": {"type": "noul"}}
STATE = {"situation": "a small state"}
ANSWER = {
    "answers": {"q": {"type": "noul", "probability": 0.8}},
    "usage": {"input_tokens": 40, "output_tokens": 1, "cost": 0.000123},
}


def test_a_jev_call_is_booked_then_settled_at_the_cost_jev_reports(database_url):
    async def scenario(pool):
        budget = budget_of(pool)
        fake = FakeJev(ANSWER)
        result = await budget.jev(fake, JEV, "p2")(STATE, QUESTIONS)
        return result, fake.calls, await booked(pool)

    result, sent, rows = with_pool(database_url, scenario)

    assert result.answers["q"].probability == 0.8
    assert sent == [(STATE, QUESTIONS)]
    (row,) = rows
    # 0.000123 USD at 1 EUR per USD: 123 millionths of a euro, the player and Jev's model id.
    assert row[1:] == ("p2", JEV.model, 40, 1, 123)


def test_a_jev_call_that_would_pass_the_match_cap_is_not_sent(database_url):
    async def scenario(pool):
        budget = budget_of(pool)
        budget.match_cap = 0  # nothing left
        fake = FakeJev(ANSWER)
        with pytest.raises(MatchPaused) as paused:
            await budget.jev(fake, JEV, "p1")(STATE, QUESTIONS)
        return paused.value.reason, fake.calls, await booked(pool)

    reason, sent, rows = with_pool(database_url, scenario)

    assert (reason, sent, rows) == ("match_cap", [], [])


@pytest.mark.parametrize(("error", "kept"), [("timeout", True), ("rate_limited", False)])
def test_a_failed_call_keeps_its_booking_unless_it_was_refused(database_url, error, kept):
    async def scenario(pool):
        fake = FakeJev(JevError(error))
        with pytest.raises(JevError):
            await budget_of(pool).jev(fake, JEV, "p1")(STATE, QUESTIONS)
        return await booked(pool)

    (row,) = with_pool(database_url, scenario)

    assert (row[-1] > 0) is kept  # the upper bound stays, or a refused call costs nothing


def test_the_api_refuses_jev_repair_unless_the_server_allows_it(database_url, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.delenv(ALLOW_JEV, raising=False)
    with TestClient(app) as client:
        response = client.post(
            "/matches", json={"game": "toy", "settings": {"answer_repair": "v2"}}
        )

        assert response.status_code == 403
        assert ALLOW_JEV in response.text
        assert client.get("/matches").json() == []
        # v1, the deterministic repair, needs no switch.
        ok = client.post("/matches", json={"game": "toy", "settings": {"answer_repair": "v1"}})
        assert ok.status_code == 201


__all__ = ["NOVEMBER"]
