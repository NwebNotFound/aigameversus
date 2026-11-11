"""Garbled tool calls of real models, read as kindly as is safe.

The garbage below is what gpt-luna sent in a heads-up Poker match: 14 of its
66 answers were rejected for the format of a call it clearly meant.
"""

import asyncio
import json

import pytest

from arena.agents import runner
from arena.agents.arguments import (
    COERCED_NUMBERS,
    EXTRACTED_JSON,
    IGNORED_EXTRA_KEYS,
    IGNORED_NON_OBJECT,
    IGNORED_THOUGHT,
    read_arguments,
)
from arena.agents.mock_llm import MockLLM, tool_call
from arena.agents.model import ModelReply, ToolCall
from arena.agents.runner import ModelAgent
from arena.engine.match import Match
from arena.engine.types import ToolSpec
from games.toy.plugin import ToyGame
from tests.agents.test_model_match import HAND_SIZE, LOWEST, no_pause, of_type

CHECK = ToolSpec(name="check", description="Check.", parameters={"type": "object"})
RAISE = ToolSpec(
    name="raise_to",
    description="Raise.",
    parameters={
        "type": "object",
        "properties": {"amount": {"type": "integer"}},
        "required": ["amount"],
        "additionalProperties": False,
    },
)


def read(raw, spec=RAISE):
    return read_arguments(raw, spec, "thought")


@pytest.mark.parametrize(
    "raw",
    [
        '{"\\u00e2\\u20ac\\udc9d": ""}',  # mojibake key on a tool that takes none
        '{"": ""}',
        '"check"',  # not an object at all
        "null",
        '{"thought": "fine", "stray": 1}',
    ],
)
def test_a_tool_without_arguments_ignores_whatever_garbage_comes_with_it(raw):
    arguments, repairs = read(raw, CHECK)

    assert {k: v for k, v in arguments.items() if k != "thought"} == {}
    assert set(repairs) <= {IGNORED_EXTRA_KEYS, IGNORED_NON_OBJECT}
    assert repairs


def test_the_object_is_found_in_reasoning_text_around_it():
    raw = 'I will raise now } } (oops syntax) {"amount": 40, "thought": "pressure"} (Malformed) {'

    assert read(raw) == ({"amount": 40, "thought": "pressure"}, [EXTRACTED_JSON])


def test_a_number_written_as_text_becomes_the_number_the_schema_wants():
    assert read('{"amount": " 40 "}') == ({"amount": 40}, [COERCED_NUMBERS])
    # Only an exact number: nothing is guessed.
    assert read('{"amount": "40 chips"}') == ({"amount": "40 chips"}, [])


def test_a_thought_that_is_not_text_is_dropped_and_said_so():
    assert read('{"amount": 40, "thought": {"x": 1}}') == ({"amount": 40}, [IGNORED_THOUGHT])


def test_a_clean_call_is_not_repaired():
    assert read('{"amount": 40, "thought": "ok"}') == ({"amount": 40, "thought": "ok"}, [])


@pytest.mark.parametrize("raw", ["not json at all", "[40]", '"40"', ""])
def test_a_call_with_arguments_that_cannot_be_read_stays_a_problem(raw):
    assert read(raw)[0] is None


def test_an_unknown_tool_is_left_for_the_engine_to_refuse():
    assert read('{"x": 1}', None) == ({"x": 1}, [])


# --- through a match, as a user of the runner sees it ---------------------------------


def garbled(card):
    """play_card with the right card, wrapped in the kind of text gpt-luna wrote."""

    def policy(messages, tools):
        clean = LOWEST(messages, tools).tool_calls[0]
        raw = f"(thinking) {clean.arguments} }} (Malformed) {{"
        return ModelReply(tool_calls=(ToolCall(clean.name, raw),))

    return policy


def play(scripts):
    plugin = ToyGame()
    mocks = {p: MockLLM(*scripts.get(p, [LOWEST] * HAND_SIZE)) for p in ("p1", "p2")}
    agents = {p: ModelAgent(m, plugin, sleep=no_pause) for p, m in mocks.items()}
    match = Match(plugin, agents, seed=3)
    asyncio.run(match.run())
    return match, mocks


def test_a_garbled_but_clear_move_is_played_and_marked_as_repaired():
    match, _ = play({"p1": [garbled(None)] + [LOWEST] * HAND_SIZE})

    assert of_type(match, "action_rejected", "p1") == []
    first = of_type(match, "decision", "p1")[0].data
    assert first["repairs"] == [EXTRACTED_JSON]
    assert first["raw_arguments"][0].startswith("(thinking) {")
    assert of_type(match, "decision", "p1")[1].data["repairs"] == []  # clean afterwards


def test_after_three_garbled_calls_the_tools_come_without_thought():
    # An illegal card, garbled: every answer is repaired and then rejected, so the
    # model is asked again and again, nine times in all.
    illegal = ModelReply(tool_calls=(ToolCall("play_card", '(x) {"card": 99} }'),))
    match, mocks = play({"p1": [illegal] * 20})

    offered = [tools for _, tools in mocks["p1"].calls]
    assert len(offered) > runner.MALFORMED_LIMIT + 1
    with_thought = ["thought" in t[0]["function"]["parameters"]["properties"] for t in offered]
    limit = runner.MALFORMED_LIMIT
    assert with_thought == [True] * limit + [False] * (len(offered) - limit)
    flags = [d.data["simple_schema"] for d in of_type(match, "decision", "p1")]
    assert flags[-1] is True and flags[0] is False


def test_a_rejected_call_names_exactly_what_the_tool_takes():
    wrong = tool_call("play_card", {"card": 3, "stray": True})  # stray is dropped; 3 may be legal
    match, _ = play({"p1": [tool_call("play_card", {}), wrong] + [LOWEST] * HAND_SIZE})

    error = of_type(match, "action_rejected", "p1")[0].data["error"]
    assert "'play_card' takes only: card (integer, required)." in error
    assert json.loads(json.dumps(error)) == error
