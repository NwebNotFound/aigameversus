"""POST /matches/{id}/referee: Jev's gates, one run per finished model match, the call in the
ledger, tags with spoilers only. Jev is a FakeJev and the models are LiteLLM's mock."""

import asyncio

import pytest
from fastapi.testclient import TestClient

from arena.api import referee
from arena.api.app import app
from arena.db.database import connect
from arena.jev.client import FakeJev, JevError
from tests.db.test_model_seats_api import KEY, MODELS, PLAY_3, finish
from tests.jev.test_referee import answer


@pytest.fixture
def client(database_url, monkeypatch, answer_with):
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("ARENA_ALLOW_MODEL_SEATS", "1")
    monkeypatch.setenv("ARENA_ALLOW_JEV", "1")
    monkeypatch.setenv("OPENROUTER_API_KEY", KEY)
    answer_with(**PLAY_3)
    with TestClient(app) as client:
        yield client


def played(client, **settings):
    body = {"game": "toy", "models": MODELS, "confirm_spend": True, "seed": 4}
    response = client.post("/matches", json={**body, "settings": settings})
    assert response.status_code == 201, response.text
    return finish(client, response.json()["id"])


def jev(monkeypatch, *script):
    fake = FakeJev(*script)
    monkeypatch.setattr(referee, "jev_client", lambda: fake)
    return fake


def ledger(url, match_id):
    async def read():
        pool = await connect(url)
        try:
            rows = await pool.fetch(
                "SELECT player, model, cost_micro_eur FROM model_calls"
                " WHERE match_id = $1 AND player = 'referee'",
                match_id,
            )
            return [tuple(row) for row in rows]
        finally:
            await pool.close()

    return asyncio.run(read())


def test_a_finished_model_match_is_judged_once_with_one_jev_call_booked_in_its_ledger(
    client, database_url, monkeypatch
):
    match = played(client)
    fake = jev(monkeypatch, lambda state, questions: answer(questions))

    run = client.post(f"/matches/{match['id']}/referee", json={"confirm_spend": True})

    assert run.status_code == 201, run.text
    body = run.json()
    assert body["status"] == "done" and body["reason"] is None
    assert 1 <= len(body["tags"]) <= 5
    assert all(t["validated"] is False and t["consistent_probability"] == 0.8 for t in body["tags"])
    assert len(fake.calls) == 1  # one call per match
    (row,) = ledger(database_url, match["id"])
    assert row[2] == 40  # 0.00004 USD at 1 EUR per USD, settled at Jev's usage.cost
    again = client.post(f"/matches/{match['id']}/referee", json={"confirm_spend": True})
    assert again.status_code == 409 and len(fake.calls) == 1
    assert client.get(f"/matches/{match['id']}/referee").status_code == 403  # spoilers only
    read = client.get(f"/matches/{match['id']}/referee", params={"spoilers": True}).json()
    assert read["tags"] == body["tags"]


def test_a_failed_jev_call_is_recorded_with_its_kind_and_no_tags(client, monkeypatch):
    match = played(client)
    jev(monkeypatch, JevError("timeout"))

    body = client.post(f"/matches/{match['id']}/referee", json={"confirm_spend": True}).json()

    assert (body["status"], body["reason"], body["tags"]) == ("failed", "timeout", [])


def test_the_matchs_cap_holds_for_the_referees_call(client, database_url, monkeypatch):
    match = played(client)
    fake = jev(monkeypatch, lambda state, questions: answer(questions))

    class Spent(referee.Budget):  # the match has nothing left under its cap
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.match_cap = 0

    monkeypatch.setattr(referee, "Budget", Spent)

    body = client.post(f"/matches/{match['id']}/referee", json={"confirm_spend": True}).json()

    assert (body["status"], body["reason"]) == ("failed", "cap (match_cap)")
    assert fake.calls == [] and ledger(database_url, match["id"]) == []  # never sent, never booked


def test_the_referee_needs_jev_allowed_confirm_spend_and_a_finished_model_match(
    client, monkeypatch
):
    match = played(client)
    fake = jev(monkeypatch, lambda state, questions: answer(questions))
    url = f"/matches/{match['id']}/referee"

    assert client.post(url, json={}).status_code == 422  # no confirm_spend
    assert (
        client.post(
            f"/matches/{'0' * 8}-0000-0000-0000-{'0' * 12}/referee", json={"confirm_spend": True}
        ).status_code
        == 404
    )
    bots = client.post("/matches", json={"game": "toy", "seed": 1}).json()
    finish(client, bots["id"])
    assert (
        client.post(f"/matches/{bots['id']}/referee", json={"confirm_spend": True}).status_code
        == 422
    )
    monkeypatch.delenv("ARENA_ALLOW_JEV")
    assert client.post(url, json={"confirm_spend": True}).status_code == 403
    assert fake.calls == []  # nothing was sent


def test_a_match_that_did_not_finish_is_never_judged(client, monkeypatch):
    stopped = played(client, match_budget_eur=0.000001)  # its own limit ends it at once
    fake = jev(monkeypatch, lambda state, questions: answer(questions))

    response = client.post(f"/matches/{stopped['id']}/referee", json={"confirm_spend": True})

    assert stopped["status"] == "interrupted"
    assert response.status_code == 409 and fake.calls == []
