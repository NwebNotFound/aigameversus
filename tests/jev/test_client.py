"""The Jev client: answers checked strictly, nothing sent unless allowed, errors by kind only."""

import asyncio
import json

import httpx
import pytest

from arena.jev.client import ALLOW_JEV, FakeJev, HttpJev, JevError, parse

QUESTIONS = {"move": {"type": "choice", "criteria": {"m1": "fold()", "m2": "call()"}}}
GOOD = {
    "answers": {
        "move": {
            "type": "choice",
            "choice": "m2",
            "probabilities": {"m1": 0.05, "m2": 0.95},
            "confidence": 0.9,
        }
    },
    "usage": {"input_tokens": 120, "output_tokens": 3, "cost": 0.0000048},
}


def test_a_good_answer_is_read_with_its_cost():
    result = parse(GOOD, QUESTIONS)

    assert result.answers["move"].choice == "m2"
    assert result.answers["move"].top_probability == 0.95
    assert result.usage.cost == 0.0000048


@pytest.mark.parametrize(
    "body",
    [
        {"answers": {}},
        {"answers": {"move": {"type": "noul", "probability": 0.9}}},
        {"answers": {"move": {**GOOD["answers"]["move"], "choice": "m9"}}},
        {"answers": {"move": {**GOOD["answers"]["move"], "probabilities": {"m7": 1.0}}}},
        {"nothing": True},
        "not even an object",
        # research/JEV: in [0, 1], exactly the options, summing to 1, choice = argmax
        {"answers": {"move": {**GOOD["answers"]["move"], "probabilities": {"m1": 0, "m2": 7.0}}}},
        {"answers": {"move": {**GOOD["answers"]["move"], "probabilities": {"m2": 1.0}}}},
        {"answers": {"move": {**GOOD["answers"]["move"], "probabilities": {"m1": 0.2, "m2": 0.7}}}},
        {
            "answers": {
                "move": {**GOOD["answers"]["move"], "probabilities": {"m1": -0.5, "m2": 1.5}}
            }
        },
        {"answers": {"move": {**GOOD["answers"]["move"], "choice": "m1"}}},  # not the argmax
        {**GOOD, "usage": {"cost": float("inf")}},
        {**GOOD, "usage": {"cost": float("nan")}},
    ],
)
def test_a_wrong_or_partial_answer_is_a_bad_answer(body):
    with pytest.raises(JevError) as raised:
        parse(body, QUESTIONS)

    assert raised.value.reason == "bad_answer"


def test_a_tie_for_the_top_and_float_rounding_are_still_an_answer():
    tie = {"type": "choice", "choice": "m1", "probabilities": {"m1": 0.5, "m2": 0.5}}
    rounded = {"type": "choice", "choice": "m2", "probabilities": {"m1": 0.1, "m2": 0.9000001}}

    for answer in (tie, rounded):
        assert parse({"answers": {"move": answer}}, QUESTIONS).answers["move"].choice


def test_the_real_client_sends_nothing_unless_the_server_allows_jev(monkeypatch):
    monkeypatch.delenv(ALLOW_JEV, raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-not-a-key")
    sent = []
    transport = httpx.MockTransport(lambda request: sent.append(request) or httpx.Response(200))

    with pytest.raises(JevError) as raised:
        asyncio.run(
            HttpJev("typesafe/jev-1.14", "https://jev.test/d", 5, transport=transport)(
                "s", QUESTIONS
            )
        )

    assert raised.value.reason == "disabled"
    assert sent == []


def answer_with(monkeypatch, handler):
    monkeypatch.setenv(ALLOW_JEV, "1")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-not-a-key")
    client = HttpJev(
        "typesafe/jev-1.14", "https://jev.test/d", 5, transport=httpx.MockTransport(handler)
    )
    return asyncio.run(client({"situation": "x"}, QUESTIONS))


def test_the_real_client_posts_model_state_and_questions_with_the_key(monkeypatch):
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json=GOOD)

    result = answer_with(monkeypatch, handler)

    (request,) = seen
    body = json.loads(request.content)
    assert body == {
        "model": "typesafe/jev-1.14",
        "state": {"situation": "x"},
        "questions": QUESTIONS,
    }
    assert request.headers["Authorization"] == "Bearer test-not-a-key"
    assert result.answers["move"].choice == "m2"


@pytest.mark.parametrize(
    ("handler", "reason"),
    [
        (lambda request: httpx.Response(429), "rate_limited"),
        (lambda request: httpx.Response(500, text="secret provider message"), "http"),
        (lambda request: httpx.Response(200, text="not json"), "bad_answer"),
    ],
)
def test_a_failed_call_says_only_its_kind(monkeypatch, handler, reason):
    with pytest.raises(JevError) as raised:
        answer_with(monkeypatch, handler)

    assert raised.value.reason == reason
    assert "secret" not in str(raised.value)


def test_a_timeout_is_its_own_kind(monkeypatch):
    def handler(request):
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(JevError) as raised:
        answer_with(monkeypatch, handler)

    assert raised.value.reason == "timeout"


def test_the_fake_plays_its_script_and_records_every_call():
    fake = FakeJev(GOOD, JevError("timeout"))

    first = asyncio.run(fake("state 1", QUESTIONS))
    with pytest.raises(JevError):
        asyncio.run(fake("state 2", QUESTIONS))

    assert first.answers["move"].choice == "m2"
    assert [state for state, _ in fake.calls] == ["state 1", "state 2"]
