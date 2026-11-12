"""A personality per model seat: a marked block at the end of the system message, nothing else."""

import asyncio

from arena.agents.mock_llm import MockLLM, tool_call
from arena.agents.prompt import build_messages, personality_text
from arena.agents.runner import ModelAgent
from arena.engine.match import Match
from arena.engine.types import TurnRequest
from arena.personalities import load_personalities
from games.toy.plugin import PLAY_CARD, ToyGame

KNIGHT = next(p for p in load_personalities() if p.id == "honourable_knight")
TEXT = personality_text(KNIGHT.name, KNIGHT.description, KNIGHT.speech_style)


def system_of(personality=None, observation=None):
    request = TurnRequest(
        player="p1",
        observation=observation or {"hand": [2, 7], "secret": "the other hand is 9"},
        tools=(PLAY_CARD,),
        events=(),
    )
    system, user = build_messages(
        "High Card", "The highest card wins.\n", request, personality=personality
    )
    return system["content"], user["content"]


def test_without_a_personality_the_prompt_is_what_it_was():
    plain = build_messages(
        "High Card",
        "The highest card wins.\n",
        TurnRequest(player="p1", observation={"hand": [2]}, tools=(PLAY_CARD,), events=()),
    )
    none = build_messages(
        "High Card",
        "The highest card wins.\n",
        TurnRequest(player="p1", observation={"hand": [2]}, tools=(PLAY_CARD,), events=()),
        personality=None,
    )

    assert plain == none
    assert "personality" not in plain[0]["content"].lower()


def test_a_personality_ends_the_system_message_as_a_marked_block():
    system, user = system_of(TEXT)

    head, block = system.split("# Your personality\n\n")
    assert head == system_of()[0] + "\n"  # everything above the block is unchanged
    assert block.startswith("Honourable Knight: Keeps their word even when it hurts.")
    assert "How you speak: Direct and dignified" in block
    assert block.rstrip().endswith("the rules and the goal of the game come first.")
    assert user == system_of()[1]  # the game data is not touched


def test_the_block_holds_the_config_text_only_never_game_data():
    system, _ = system_of(TEXT, observation={"hand": [2], "secret": "p2 holds the 9"})

    block = system.split("# Your personality\n\n")[1]
    assert "p2 holds the 9" not in block and "hand" not in block
    assert TEXT in block


def test_a_model_agent_with_a_personality_sends_it_and_a_match_records_it():
    plugin = ToyGame()
    knight = MockLLM(*[tool_call("play_card", {"card": c}) for c in (1, 2, 3, 4, 5)] * 4)
    plain = MockLLM(*[tool_call("play_card", {"card": c}) for c in (1, 2, 3, 4, 5)] * 4)
    agents = {"p1": ModelAgent(knight, plugin, personality=TEXT), "p2": ModelAgent(plain, plugin)}
    match = Match(plugin, agents, seed=1, personalities={"p1": "honourable_knight"})

    asyncio.run(match.run())

    assert "# Your personality" in knight.calls[0][0][0]["content"]
    assert "# Your personality" not in plain.calls[0][0][0]["content"]
    started = match.events[0]
    assert started.data["personalities"] == {"p1": "honourable_knight"}


def test_a_match_without_personalities_logs_no_personality_field():
    plugin = ToyGame()
    mock = MockLLM(*[tool_call("play_card", {"card": c}) for c in (1, 2, 3, 4, 5)] * 8)
    match = Match(plugin, {"p1": ModelAgent(mock, plugin), "p2": ModelAgent(mock, plugin)}, seed=1)

    asyncio.run(match.run())

    assert "personalities" not in match.events[0].data
