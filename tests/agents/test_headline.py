"""thought_headline: a match setting that asks every tool call for the thought in a line."""

import asyncio

import pytest

from arena.agents.mock_llm import MockLLM, tool_call
from arena.agents.prompt import HEADLINE_CHARS
from arena.agents.runner import ModelAgent
from arena.engine.match import Match
from games.poker.plugin import Poker
from games.toy.plugin import ToyGame
from tests.agents.test_model_match import HAND_SIZE, LOWEST, no_pause, of_type

ON = {"thought_headline": True}


def with_headline(text):
    def policy(messages, tools):
        call = LOWEST(messages, tools).tool_calls[0]
        card = __import__("json").loads(call.arguments)["card"]
        return tool_call("play_card", {"card": card, "thought": "long reasoning", "headline": text})

    return policy


def play(scripts, settings):
    plugin = ToyGame()
    mocks = {p: MockLLM(*scripts.get(p, [LOWEST] * HAND_SIZE)) for p in ("p1", "p2")}
    agents = {p: ModelAgent(m, plugin, settings=settings, sleep=no_pause) for p, m in mocks.items()}
    match = Match(plugin, agents, seed=3, settings=settings)
    asyncio.run(match.run())
    return match, mocks


def test_with_the_flag_every_tool_asks_for_a_headline_and_the_thought_event_keeps_it():
    match, mocks = play({"p1": [with_headline("  Low card, save the ace.  ")] * HAND_SIZE}, ON)

    schema = mocks["p1"].calls[0][1][0]["function"]["parameters"]
    assert schema["properties"]["headline"]["maxLength"] == HEADLINE_CHARS
    assert "headline" in schema["required"]
    assert list(schema["properties"])[:2] == ["thought", "headline"]
    thought = of_type(match, "thought", "p1")[0]
    assert thought.data == {
        "player": "p1",
        "text": "long reasoning",
        "headline": "Low card, save the ace.",
    }
    assert thought.visible_to == ()
    assert "headline" not in of_type(match, "action_accepted", "p1")[0].data["arguments"]
    assert of_type(match, "match_started")[0].data["thought_headline"] is True


def test_a_headline_longer_than_its_limit_is_cut():
    match, _ = play({"p1": [with_headline("x" * 500)] * HAND_SIZE}, ON)

    assert len(of_type(match, "thought", "p1")[0].data["headline"]) == HEADLINE_CHARS


def test_without_the_flag_nothing_asks_for_or_keeps_a_headline():
    match, mocks = play({"p1": [with_headline("ignored")] * HAND_SIZE}, {})

    schema = mocks["p1"].calls[0][1][0]["function"]["parameters"]
    assert "headline" not in schema["properties"]
    assert "headline" not in schema.get("required", [])
    assert all("headline" not in e.data for e in of_type(match, "thought"))
    assert of_type(match, "match_started")[0].data["thought_headline"] is False


@pytest.mark.parametrize("value", ["yes", 1, None])
def test_the_flag_is_true_or_false(value):
    with pytest.raises(ValueError, match="thought_headline"):
        Match(ToyGame(), {"p1": None, "p2": None}, seed=1, settings={"thought_headline": value})


def test_games_never_see_the_flag():
    match = Match(Poker(), {"p1": None, "p2": None}, seed=1, settings=ON)  # Poker refuses unknowns
    assert match.settings == ON
