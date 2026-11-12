"""The `decision` event: what each model move took, for spectators and analyses."""

import asyncio
import itertools
from dataclasses import replace

from arena.agents.mock_llm import MockLLM, tool_call
from arena.agents.model import ModelError, ModelReply, Usage
from arena.agents.random_bot import random_bots
from arena.agents.runner import ModelAgent
from arena.engine.match import Match
from games.toy.plugin import ToyGame
from tests.agents.test_model_match import HAND_SIZE, LOWEST, no_pause, of_type, prompts

PLAYERS = ["p1", "p2"]


def ticking(step=0.25):
    """A clock that moves on by `step` seconds every time it is read."""
    ticks = itertools.count()
    return lambda: next(ticks) * step


def play(scripts, clock=None, players=PLAYERS):
    plugin = ToyGame()
    mocks = {p: MockLLM(*scripts.get(p, [LOWEST] * HAND_SIZE)) for p in players}
    agents = {p: ModelAgent(mock, plugin, sleep=no_pause) for p, mock in mocks.items()}
    match = Match(plugin, agents, seed=3, clock=clock)
    asyncio.run(match.run())
    return match, mocks


def card(n, used):
    return tool_call("play_card", {"card": n}, usage=Usage(*used))


def lowest(used):
    """The lowest card of the hand, with these tokens reported."""
    return lambda messages, tools: replace(LOWEST(messages, tools), usage=Usage(*used))


def test_every_model_move_says_its_time_tokens_and_retries_for_spectators_only():
    # p1: a failed call tried again, an illegal card, then a legal one; tokens per answer.
    p1 = [ModelError("RateLimitError"), card(99, (1000, 50, 20)), lowest((1100, 40, 10))]
    match, mocks = play({"p1": p1 + [LOWEST] * HAND_SIZE}, clock=ticking())

    first = of_type(match, "decision", "p1")[0]
    assert first.visible_to == ()
    assert first.data == {
        "player": "p1",
        "answers": 2,  # the rejected answer and the accepted one
        "latency_ms": 250,  # the clock is read once at the start and once at the end
        "tokens_in": 2100,
        "tokens_out": 90,
        "reasoning_tokens": 30,
        "retries": 1,
        "rate_limits": 1,  # the retry was a rate limit
        "cutoffs": 0,
        "fallback": None,
        "repairs": [],
        "raw_arguments": [],
        "simple_schema": False,
    }
    position = match.events.index(first)
    assert match.events[position - 1].type == "action_accepted"
    assert len(of_type(match, "decision")) == 2 * HAND_SIZE  # every move of both models
    for mock in mocks.values():
        assert "decision" not in prompts(mock) and "latency_ms" not in prompts(mock)


def test_a_move_without_reported_tokens_has_null_counts():
    match, _ = play({}, clock=ticking())

    data = of_type(match, "decision", "p2")[0].data
    assert (data["tokens_in"], data["tokens_out"], data["reasoning_tokens"]) == (None, None, None)
    assert data["latency_ms"] == 250


def test_without_a_clock_the_log_has_no_time_and_stays_the_same_every_time():
    first, _ = play({})
    second, _ = play({})

    assert {e.data["latency_ms"] for e in of_type(first, "decision")} == {None}
    assert first.events == second.events


def test_a_move_that_ends_in_a_random_move_says_why():
    wrong = [card(99, (10, 1, None))] * 3  # three illegal answers: the fallback plays
    match, _ = play({"p1": wrong + [LOWEST] * HAND_SIZE}, clock=ticking())

    data = of_type(match, "decision", "p1")[0].data
    assert (data["answers"], data["fallback"], data["tokens_in"]) == (3, "rejected", 30)
    assert data["reasoning_tokens"] is None


def test_a_seat_whose_model_gave_up_says_so_on_every_move():
    match, _ = play({"p1": [ModelError("AuthenticationError", retryable=False)]})

    moves = of_type(match, "decision", "p1")
    assert len(moves) == HAND_SIZE
    assert {(m.data["answers"], m.data["fallback"]) for m in moves} == {(0, "agent_failed")}


def test_bots_leave_no_decision_events():
    plugin = ToyGame()
    match = Match(plugin, random_bots(plugin, PLAYERS, 3), seed=3, clock=ticking())
    asyncio.run(match.run())

    assert of_type(match, "decision") == []


def test_an_answer_cut_off_at_the_output_limit_is_counted_on_its_move():
    cut = ModelReply(text="I think that the best card is", cut_off=True)  # no tool call
    match, _ = play({"p1": [cut, LOWEST] + [LOWEST] * HAND_SIZE}, clock=ticking())

    first = of_type(match, "decision", "p1")[0].data
    assert (first["answers"], first["cutoffs"], first["rate_limits"]) == (2, 1, 0)
