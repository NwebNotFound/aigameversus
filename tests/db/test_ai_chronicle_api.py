"""POST/GET /matches/{id}/chronicle/ai: paid once, cached, capped at EUR 0.03, fact-checked.
The model is a metered mock: nothing is spent."""

import asyncio
from uuid import NAMESPACE_URL, uuid5

import pytest
from fastapi.testclient import TestClient

from arena.agents.mock_llm import MockLLM
from arena.agents.model import ModelReply
from arena.api import chronicle
from arena.api.app import app
from arena.config import load_config
from arena.db.database import connect, migrate
from arena.db.ledger import Ledger
from tests.chronicle.test_ai_chronicle import echo
from tests.db.test_chronicle_api import finish, start

MODEL = next(iter(load_config().models))
NEW = {"style": "news", "lang": "en", "model": MODEL, "confirm_spend": True}


@pytest.fixture
def client(database_url, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("ARENA_ALLOW_MODEL_SEATS", "1")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-not-a-key")
    with TestClient(app) as client:
        yield client


def model(monkeypatch, make=lambda: echo(lambda n, t: f"In brief: {t}")):
    calls = []

    def call(budget, model_id):
        calls.append(model_id)
        return budget.meter("chronicler", model_id, make())

    monkeypatch.setattr(chronicle, "chronicle_call", call)
    return calls


def booked(url):
    async def read():
        pool = await connect(url)
        try:
            return [
                tuple(r)
                for r in await pool.fetch(
                    "SELECT player, cost_micro_eur, match_id FROM model_calls ORDER BY id"
                )
            ]
        finally:
            await pool.close()

    return asyncio.run(read())


def test_a_finished_match_is_retold_once_labelled_then_served_from_the_cache(
    client, database_url, monkeypatch
):
    match_id = start(client, "liars_deck", players=3, seed=5)
    finish(client, match_id)
    calls = model(monkeypatch)
    url = f"/matches/{match_id}/chronicle/ai"

    first = client.post(url, json=NEW)

    assert first.status_code == 201, first.text
    body = first.json()
    assert body["ai_written"] and "AI-written" in body["label"] and body["model"] == MODEL
    assert all(check["ai"] for check in body["checks"])
    assert all(c["text"].startswith("In brief: ") for c in body["chronicle"]["chapters"])
    rows = booked(database_url)
    assert [player for player, *_ in rows] == ["chronicler"] and 0 < rows[0][1] <= 30_000
    again = client.post(url, json=NEW)
    assert again.status_code == 200 and again.json() == body and len(calls) == 1  # paid once
    read = client.get(url, params={"model": MODEL, "style": "news", "lang": "en"})
    assert read.json() == body
    other = client.get(url, params={"model": MODEL, "style": "epic", "lang": "en"})
    assert other.status_code == 404  # another style is another chronicle
    assert client.get(f"/matches/{match_id}/chronicle").json()["chapters"]  # templates stay


def test_an_ai_chronicle_needs_the_switch_the_spend_box_and_a_finished_match(client, monkeypatch):
    calls = model(monkeypatch)
    match_id = start(client, "poker", players=3, seed=2)
    finish(client, match_id)
    url = f"/matches/{match_id}/chronicle/ai"

    assert client.post(url, json={**NEW, "confirm_spend": False}).status_code == 422
    assert client.post(url, json={**NEW, "model": "no/such"}).status_code == 422
    monkeypatch.delenv("ARENA_ALLOW_MODEL_SEATS")
    assert client.post(url, json=NEW).status_code == 403
    assert calls == []


def test_a_chronicle_whose_worst_case_passes_its_cap_is_refused_before_any_call(
    client, database_url, monkeypatch
):
    match_id = start(client, "liars_deck", players=3, seed=5)
    finish(client, match_id)
    calls = model(monkeypatch)
    monkeypatch.setattr(chronicle, "CHRONICLE_CAP_EUR", chronicle.Decimal("0.000001"))

    response = client.post(f"/matches/{match_id}/chronicle/ai", json=NEW)

    assert response.status_code == 422 and "above its 0.000001 EUR cap" in response.text
    assert calls == [] and booked(database_url) == []


def test_a_failed_write_is_recorded_and_may_be_tried_again_under_the_same_cap(
    client, database_url, monkeypatch
):
    match_id = start(client, "liars_deck", players=3, seed=5)
    finish(client, match_id)

    class Broken:
        async def __call__(self, messages, tools):
            raise RuntimeError("provider down")

    model(monkeypatch, make=Broken)
    url = f"/matches/{match_id}/chronicle/ai"
    assert client.post(url, json=NEW).status_code == 502

    model(monkeypatch)
    assert client.post(url, json=NEW).status_code == 201
    rows = booked(database_url)
    assert len(rows) == 2 and {player for player, *_ in rows} == {"chronicler"}
    own = uuid5(NAMESPACE_URL, f"chronicle/{match_id}/news/en/{MODEL}")
    assert {job for *_, job in rows} == {own}  # both under one id: one cap for every retry
    assert client.post(url, json=NEW).status_code == 200 and len(booked(database_url)) == 2


def test_a_retry_cannot_spend_past_what_earlier_attempts_left_of_the_cap(
    client, database_url, monkeypatch
):
    match_id = start(client, "liars_deck", players=3, seed=5)
    finish(client, match_id)

    class Broken:
        async def __call__(self, messages, tools):
            raise RuntimeError("provider down")

    model(monkeypatch, make=Broken)
    url = f"/matches/{match_id}/chronicle/ai"
    for _ in range(40):  # each failed call keeps its upper bound booked
        if client.post(url, json=NEW).json()["detail"].startswith("The AI chronicle failed (cap"):
            break
    spent = sum(cost for _, cost, _ in booked(database_url))
    assert spent <= 30_000  # never past EUR 0.03, however often it is tried
    assert client.post(url, json=NEW).status_code == 502


def sql(url, query, *args):
    async def go():
        pool = await connect(url)
        try:
            return await pool.fetch(query, *args)
        finally:
            await pool.close()

    return asyncio.run(go())


def test_a_running_chronicle_is_another_requests_until_it_is_stale(
    client, database_url, monkeypatch
):
    match_id = start(client, "liars_deck", players=3, seed=5)
    finish(client, match_id)
    calls = model(monkeypatch)
    sql(
        database_url,
        "INSERT INTO ai_chronicles (match_id, style, lang, model, job_id, status, created_at)"
        " VALUES ($1, 'news', 'en', $2, $3, 'running', now())",
        match_id,
        MODEL,
        uuid5(NAMESPACE_URL, f"chronicle/{match_id}/news/en/{MODEL}"),
    )
    url = f"/matches/{match_id}/chronicle/ai"

    assert client.post(url, json=NEW).status_code == 409  # another request writes it now
    assert calls == [] and booked(database_url) == []

    # The request that claimed it died (restart, cancel): after 10 minutes it is taken over.
    sql(database_url, "UPDATE ai_chronicles SET created_at = now() - interval '11 minutes'")

    assert client.post(url, json=NEW).status_code == 201 and len(calls) == 1


def test_an_answer_with_no_usable_chapter_is_a_failure_that_may_be_retried(
    client, database_url, monkeypatch
):
    match_id = start(client, "liars_deck", players=3, seed=5)
    finish(client, match_id)
    model(monkeypatch, make=lambda: MockLLM(ModelReply(text="Once upon a time")))
    url = f"/matches/{match_id}/chronicle/ai"

    response = client.post(url, json=NEW)

    assert response.status_code == 502 and "did not call write_chronicle" in response.text
    assert (
        client.get(url, params={"model": MODEL, "style": "news", "lang": "en"}).status_code == 404
    )
    model(monkeypatch)
    assert client.post(url, json=NEW).status_code == 201  # tried again, under the same cap
    own = uuid5(NAMESPACE_URL, f"chronicle/{match_id}/news/en/{MODEL}")
    assert {job for *_, job in booked(database_url)} == {own}


def test_a_chronicle_or_qualification_answer_is_no_move_in_the_estimates_history(database_url):
    async def go():
        pool = await connect(database_url)
        try:
            await migrate(pool)
            for player, output in [("p1", 100), ("chronicler", 5000), ("q-A", 5000)]:
                await pool.execute(
                    "INSERT INTO model_calls "
                    "(match_id, player, model, called_at, output_tokens, cost_micro_eur) "
                    "VALUES (gen_random_uuid(), $1, 'm', now(), $2, 1)",
                    player,
                    output,
                )
            return await Ledger(pool).output_tokens(["m"])
        finally:
            await pool.close()

    assert asyncio.run(go()) == {"m": (1, 100.0)}
