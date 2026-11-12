"""adaptive_output (D-143): a cut-off answer is asked again with a larger output limit."""

import asyncio

import pytest

from arena.agents import estimate as estimating
from arena.agents.mock_llm import MockLLM
from arena.agents.model import ModelReply, Usage
from arena.agents.runner import ModelAgent, OutputLimits, escalation
from arena.config import load_config
from arena.engine.match import Match
from arena.engine.types import game_settings
from games.toy.plugin import ToyGame
from tests.agents.test_model_match import HAND_SIZE, LOWEST, no_pause, of_type

ON = {"adaptive_output": "on"}
LIMITS = OutputLimits(start=1500, ceiling=8000)
CUT = ModelReply(text="I was thinking about the cards and", cut_off=True, usage=Usage(900, 1500))


def play(script, settings, limits=LIMITS):
    plugin = ToyGame()
    mock = MockLLM(*script)
    agents = {
        "p1": ModelAgent(mock, plugin, settings=settings, output=limits, sleep=no_pause),
        "p2": ModelAgent(MockLLM(LOWEST), plugin, settings=settings, sleep=no_pause),
    }
    match = Match(plugin, agents, seed=3, settings=settings)
    asyncio.run(match.run())
    return match, mock


def test_the_chain_doubles_up_to_the_ceiling():
    assert escalation(LIMITS) == [1500, 3000, 6000, 8000]
    assert escalation(OutputLimits(4000, 4000)) == [4000]


def test_off_by_default_a_cut_off_answer_goes_to_the_engines_correction_as_before():
    match, mock = play([CUT] + [LOWEST] * HAND_SIZE, {})

    first = of_type(match, "decision", "p1")[0].data
    assert mock.output_limits[:2] == [None, None]  # never raised
    assert first["answers"] == 2 and first["cutoffs"] == 1
    assert "output_limits" not in first  # the event is what it was before the setting


def test_on_the_same_prompt_is_asked_again_with_twice_the_limit_and_the_move_is_played():
    match, mock = play([CUT] + [LOWEST] * HAND_SIZE, ON)

    first = of_type(match, "decision", "p1")[0].data
    assert mock.output_limits[:2] == [None, 3000]
    assert mock.calls[0] == mock.calls[1]  # the very same prompt and tools
    assert first["answers"] == 1 and first["cutoffs"] == 0  # one answer, finished
    assert first["output_limits"] == [[1500, 3000]]
    assert first["tokens_in"] >= 900  # both calls are counted
    assert of_type(match, "action_rejected", "p1") == []


def test_it_stops_at_the_ceiling_and_then_the_engine_corrects_as_before():
    match, mock = play([CUT, CUT, CUT, CUT] + [LOWEST] * HAND_SIZE, ON)

    first = of_type(match, "decision", "p1")[0].data
    assert mock.output_limits[:4] == [None, 3000, 6000, 8000]
    assert first["output_limits"][0] == [1500, 3000, 6000, 8000]
    assert first["cutoffs"] == 1 and first["answers"] == 2  # the correction played the move


def test_a_cut_off_answer_that_still_holds_a_usable_call_is_not_asked_again():
    def finished_but_marked(messages, tools):
        move = LOWEST(messages, tools)
        return ModelReply(text=move.text, tool_calls=move.tool_calls, cut_off=True)

    match, mock = play([finished_but_marked] + [LOWEST] * HAND_SIZE, ON)

    assert mock.output_limits[0] is None and mock.output_limits[1] is None
    assert "output_limits" not in of_type(match, "decision", "p1")[0].data


def test_the_setting_is_the_engines_and_must_be_off_or_on():
    assert game_settings(ON) == {}  # the toy game refuses unknown settings, so it never sees it
    with pytest.raises(ValueError, match="adaptive_output"):
        Match(ToyGame(), {"p1": None, "p2": None}, seed=1, settings={"adaptive_output": "yes"})


def test_the_estimate_shows_the_worst_case_of_raised_limits_only_when_it_is_on():
    config = load_config()
    seats = {"p1": "deepseek-flash", "p2": None}

    off = asyncio.run(estimating.estimate(ToyGame(), seats, {}, config, {}))["p1"]
    on = asyncio.run(estimating.estimate(ToyGame(), seats, ON, config, {}))["p1"]

    assert on.estimate_micro_eur == off.estimate_micro_eur  # the expected cost: unchanged
    assert off.worst_case_micro_eur == off.estimate_micro_eur  # no history: already the limit
    assert on.worst_case_micro_eur > 3 * off.worst_case_micro_eur  # 1500+3000+6000+8000


class Slow:
    """A model whose raised calls take `seconds`: the first answer is cut off, then it plays."""

    def __init__(self, seconds):
        self.seconds, self.limits = seconds, []

    async def __call__(self, messages, tools, *, max_output_tokens=None):
        self.limits.append(max_output_tokens)
        if max_output_tokens is None:
            return CUT
        await asyncio.sleep(self.seconds)
        return LOWEST(messages, tools)


def test_a_seat_with_adaptive_output_gets_the_time_of_every_call_of_its_chain():
    plugin = ToyGame()
    slow = Slow(0.15)
    limits = OutputLimits(start=100, ceiling=200)  # two calls: 0.1 s each, 0.2 s together
    agents = {
        "p1": ModelAgent(slow, plugin, settings=ON, output=limits, sleep=no_pause),
        "p2": ModelAgent(MockLLM(LOWEST), plugin, settings=ON, sleep=no_pause),
    }
    match = Match(plugin, agents, seed=3, settings=ON, turn_timeout=0.1)
    asyncio.run(match.run())

    assert agents["p1"].turn_time_factor == 2 and agents["p2"].turn_time_factor == 1
    assert slow.limits[:2] == [None, 200]
    first = of_type(match, "decision", "p1")[0].data
    assert first["fallback"] is None  # the raised call had its time and played the move
