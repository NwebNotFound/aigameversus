"""A Poker match played by mock-LLM seats through the agent runner."""

import asyncio
import json
import re

from arena.agents.mock_llm import MockLLM, tool_call
from arena.agents.runner import ModelAgent
from arena.engine.match import Match
from arena.engine.replay import replay
from arena.engine.types import MESSAGE
from games.poker.plugin import Poker

PLAYERS = ["p1", "p2", "p3"]


def situation(messages):
    block = re.search(r"<situation>\n(.*)\n</situation>", messages[1]["content"]).group(1)
    return json.loads(block)


def tool_names(tools):
    return {tool.get("function", tool).get("name") for tool in tools}


def player(messages, tools):
    """Talk once per turn, raise the minimum with a pair, otherwise check or call."""
    seen = situation(messages)
    names = tool_names(tools)
    if "table_talk" in names:
        return tool_call("table_talk", {"text": f"Hand {seen['hand']}, nobody scares me."})
    ranks = [card[0] for card in seen["your_cards"]]
    if "raise" in names and ranks[0] == ranks[1]:
        return tool_call("raise", {"amount": seen["min_raise_to"]}, text=f"pair: {ranks}")
    if "check" in names:
        return tool_call("check", {}, text="free card")
    return tool_call("call", {}, text=f"calling {seen['to_call']}")


async def no_pause(seconds):
    pass


def test_mock_llm_seats_play_a_match_through_the_agent_runner():
    plugin = Poker()
    # p1 first raises below the minimum, so the server's correction is exercised.
    mocks = {
        "p1": MockLLM(tool_call("raise", {"amount": 25}), player),
        "p2": MockLLM(player),
        "p3": MockLLM(player),
    }
    agents = {p: ModelAgent(mock, plugin, sleep=no_pause) for p, mock in mocks.items()}
    match = Match(plugin, agents, seed=3, settings={"hand_limit": 4})

    placements = asyncio.run(match.run())

    assert match.state.phase == "over"
    assert sorted(p.player for p in placements) == PLAYERS
    rejected = [e for e in match.events if e.type == "action_rejected"]
    assert rejected and "less than the minimum of 40" in json.dumps(rejected[0].data)
    assert any(
        e.type == MESSAGE and e.data["text"] == "Hand 1, nobody scares me." for e in match.events
    )
    assert any(e.type == "showdown" for e in match.events)
    for mock in mocks.values():
        for messages, _ in mock.calls:
            assert "free card" not in json.dumps(messages)  # thoughts never reach a prompt
    assert sum(match.state.stacks.values()) == 3000
    assert replay(Poker(), match.events) == match.state
