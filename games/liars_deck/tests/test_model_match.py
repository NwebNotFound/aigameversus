"""A whole Liar's Deck match played by mock-LLM seats through the agent runner."""

import asyncio
import json
import re

from arena.agents.mock_llm import MockLLM, tool_call
from arena.agents.runner import ModelAgent
from arena.engine.match import Match
from arena.engine.replay import replay
from arena.engine.types import MESSAGE
from games.liars_deck.plugin import LiarsDeck

PLAYERS = ["p1", "p2", "p3"]


def situation(messages):
    block = re.search(r"<situation>\n(.*)\n</situation>", messages[1]["content"]).group(1)
    return json.loads(block)


def tool_names(tools):
    return {tool.get("function", tool).get("name") for tool in tools}


def table_player(messages, tools):
    """Talk once per turn, call 'Liar!' on plays of 2 or more cards, else play one card."""
    seen = situation(messages)
    names = tool_names(tools)
    if "table_talk" in names:
        return tool_call("table_talk", {"text": f"Round {seen['round']}, I trust nobody."})
    last = seen["last_play"]
    if "call_liar" in names and (last["count"] >= 2 or "play_cards" not in names):
        return tool_call("call_liar", {"text": "Liar!"}, text="Two cards smells like a bluff.")
    return tool_call(
        "play_cards",
        {"card_ids": [seen["hand"][0]], "claim_text": f"One {seen['table_card']}."},
        text=f"I hold {seen['hand']}.",
    )


def no_pause(seconds):
    async def nothing():
        pass

    return nothing()


def test_mock_llm_seats_finish_a_match_through_the_agent_runner():
    plugin = LiarsDeck()
    # p1 first names a card it does not hold, so the server's correction is exercised.
    mocks = {
        "p1": MockLLM(tool_call("play_cards", {"card_ids": ["Z9"]}), table_player),
        "p2": MockLLM(table_player),
        "p3": MockLLM(table_player),
    }
    agents = {p: ModelAgent(mock, plugin, sleep=no_pause) for p, mock in mocks.items()}
    match = Match(plugin, agents, seed=6, settings={"variant": "devil_card"})

    placements = asyncio.run(match.run())

    assert len(match.state.alive) == 1
    assert sorted(p.player for p in placements) == PLAYERS
    rejected = [e for e in match.events if e.type == "action_rejected"]
    assert rejected and "You do not hold Z9" in json.dumps(rejected[0].data)
    talk = [e.data for e in match.events if e.type == MESSAGE]
    assert {"player": "p2", "text": "Round 1, I trust nobody."} in talk
    assert any(e.type == "liar_called" for e in match.events)
    # Thoughts stay out of every prompt a model got, including its own later ones.
    for mock in mocks.values():
        for messages, _ in mock.calls:
            assert "I hold [" not in json.dumps(messages)
    assert replay(LiarsDeck(), match.events) == match.state
