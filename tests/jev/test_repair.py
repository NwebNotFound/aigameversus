"""Tier 2 of the move repair: Jev picks among legal moves only, above a threshold, never speech."""

import asyncio

import pytest

from arena.engine.types import Action, RepairRequest, ToolSpec
from arena.jev.client import FakeJev, JevError
from arena.jev.config import load_jev_config
from arena.jev.repair import JevRepairer, options_of, state_of

CONFIG = load_jev_config()

FOLD = ToolSpec(
    name="fold", description="Give up.", parameters={"type": "object", "properties": {}}
)
RAISE = ToolSpec(
    name="raise",
    description="Raise.",
    parameters={
        "type": "object",
        "properties": {"amount": {"type": "integer", "minimum": 40, "maximum": 1000}},
        "required": ["amount"],
    },
)
TALK = ToolSpec(
    name="table_talk",
    description="Say something.",
    parameters={
        "type": "object",
        "properties": {"text": {"type": "string", "maxLength": 400}},
        "required": ["text"],
    },
)
VOTE = ToolSpec(
    name="vote",
    description="Vote.",
    parameters={
        "type": "object",
        "properties": {
            "target": {"type": ["string", "null"], "enum": [None, "p2", "p3"]},
            "reason": {"type": "string", "maxLength": 480},
        },
        "required": ["target"],
    },
)


def request(tools, attempts=(), thought=None, observation=None):
    return RepairRequest(
        game="Poker",
        player="p1",
        observation=observation or {"hand": ["As", "Kd"], "pot": 120},
        tools=list(tools),
        summary=None,
        thought=thought,
        attempts=list(attempts),
        raw=[],
    )


def choice(probabilities, chosen=None):
    best = chosen or max(probabilities, key=probabilities.get)
    return lambda state, questions: {
        "answers": {
            "intended_move": {"type": "choice", "choice": best, "probabilities": probabilities}
        },
        "usage": {"input_tokens": 300, "cost": 0.000012},
    }


def test_speech_is_never_an_option_and_optional_free_text_is_dropped():
    candidates = [
        Action(tool="table_talk", arguments={"text": "I fold"}),
        Action(tool="vote", arguments={"target": "p2", "reason": "random words"}),
        Action(tool="vote", arguments={"target": "p3"}),
        Action(tool="fold", arguments={}),
    ]

    options = options_of(candidates, [TALK, VOTE, FOLD], limit=16)

    assert options == [
        Action(tool="vote", arguments={"target": "p2"}),
        Action(tool="fold", arguments={}),
        Action(tool="vote", arguments={"target": "p3"}),
    ]


def test_a_bet_is_offered_as_bounds_middle_and_the_amount_the_model_tried():
    candidates = [
        Action(tool="raise", arguments={"amount": 377}),
        Action(tool="fold", arguments={}),
    ]
    tried = [{"tool": "raise", "arguments": {"amount": 250}, "error": "not your turn"}]

    options = options_of(candidates, [RAISE, FOLD], limit=16, attempts=tried)

    amounts = sorted(o.arguments["amount"] for o in options if o.tool == "raise")
    assert amounts == [40, 250, 520, 1000]  # min, tried, middle, max: no random 377


def test_options_keep_every_tool_before_a_tool_gets_a_second_one():
    candidates = [Action(tool="vote", arguments={"target": t}) for t in ("p2", "p3", None)]
    candidates.append(Action(tool="fold", arguments={}))

    options = options_of(candidates, [VOTE, FOLD], limit=2)

    assert [o.tool for o in options] == ["vote", "fold"]


@pytest.mark.parametrize(("top", "played"), [(0.95, True), (0.90, True), (0.89, False)])
def test_the_pick_plays_only_at_or_above_the_threshold_on_the_top_probability(top, played):
    fake = FakeJev(choice({"m1": top, "m2": round(1 - top, 4)}))
    candidates = [
        Action(tool="vote", arguments={"target": "p2"}),
        Action(tool="fold", arguments={}),
    ]

    outcome = asyncio.run(
        JevRepairer(lambda p: fake, CONFIG).repair(request([VOTE, FOLD]), candidates)
    )

    assert outcome.top_probability == top
    assert outcome.options == 2
    assert (outcome.action == Action(tool="vote", arguments={"target": "p2"})) is played
    assert outcome.reason == ("accepted" if played else "below_threshold")


def test_the_most_probable_option_plays_even_if_jevs_choice_field_says_another():
    fake = FakeJev(choice({"m1": 0.04, "m2": 0.96}, chosen="m1"))
    candidates = [
        Action(tool="vote", arguments={"target": "p2"}),
        Action(tool="fold", arguments={}),
    ]

    outcome = asyncio.run(
        JevRepairer(lambda p: fake, CONFIG).repair(request([VOTE, FOLD]), candidates)
    )

    assert outcome.action == Action(tool="fold", arguments={})


@pytest.mark.parametrize("reason", ["timeout", "rate_limited", "bad_answer", "disabled"])
def test_a_failed_jev_call_repairs_nothing_and_says_why(reason):
    fake = FakeJev(JevError(reason))

    outcome = asyncio.run(
        JevRepairer(lambda p: fake, CONFIG).repair(
            request([FOLD]), [Action(tool="fold", arguments={})]
        )
    )

    assert (outcome.action, outcome.reason) == (None, reason)


def test_without_options_jev_is_not_asked():
    fake = FakeJev()

    outcome = asyncio.run(
        JevRepairer(lambda p: fake, CONFIG).repair(
            request([TALK]), [Action(tool="table_talk", arguments={"text": "hi"})]
        )
    )

    assert outcome.reason == "no_options" and fake.calls == []


def test_the_state_holds_the_players_view_reasoning_tail_and_broken_calls_only():
    long_thought = "x" * 2000 + " so I fold."
    broken = [
        {
            "player": "p1",
            "tool": "fold!",
            "arguments": None,
            "error": "Tool 'fold!' is not available",
        }
    ]

    state = state_of(request([FOLD], broken, long_thought), CONFIG)

    assert state["model_reasoning_end"].endswith("so I fold.")
    assert len(state["model_reasoning_end"]) == CONFIG.reasoning_chars
    assert state["broken_calls"] == [
        {"tool": "fold!", "arguments": None, "error": "Tool 'fold!' is not available"}
    ]
    assert '"hand": ["As", "Kd"]' in state["situation"]
    assert set(state) == {
        "game",
        "player",
        "situation",
        "model_reasoning_end",
        "broken_calls",
        "raw_calls",
        "task",
    }


def test_the_config_has_a_threshold_for_every_option_count_it_offers():
    assert [CONFIG.threshold(n) for n in (2, 3, 4, 5, 16)] == [0.9] * 5
    with pytest.raises(StopIteration):
        CONFIG.threshold(17)
