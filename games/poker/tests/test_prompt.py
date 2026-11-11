"""The prompt of Poker: versions, summary, no leaks, every tool named, size, golden files."""

import asyncio
import os
import re
from pathlib import Path

import pytest

from arena.agents.prompt import build_messages
from arena.agents.random_bot import RandomBot
from arena.engine.match import Match
from arena.engine.rng import derive_rng
from games.poker import prompt
from games.poker.plugin import Poker

GOLDEN = Path(__file__).parent / "golden"
CARD = re.compile(r"(?<!of )b[2-9TJQKA][cdhs]b")  # not "pair of 5s"


class Spy(RandomBot):
    def __init__(self, plugin, rng, seen):
        super().__init__(plugin, rng)
        self.seen = seen

    async def act(self, request):
        self.seen.append(request)
        return await super().act(request)


def requests_of(seed, players=3, settings=None):
    plugin, seen = Poker(), []
    agents = {f"p{i}": Spy(plugin, derive_rng(seed, "spy", i), seen) for i in range(1, players + 1)}
    asyncio.run(Match(plugin, agents, seed=seed, settings=settings or {"hand_limit": 4}).run())
    return seen


def test_the_versions_are_p1_as_it_was_and_p2_with_new_rules():
    old = prompt.rules_text("poker-p1")
    new = prompt.rules_text("poker-p2")

    assert old == (Path(prompt.__file__).parent / "rules.md").read_text(encoding="utf-8")
    assert "How to play well" in new and "How to play well" not in old
    assert len(new.split()) < 1100


def test_the_prompt_version_is_a_setting_that_is_checked_and_reported():
    plugin = Poker()

    assert plugin.prompt_version({}) == "poker-p1"
    assert plugin.prompt_version({"prompt_version": "poker-p2"}) == "poker-p2"
    plugin.initial_state(["p1", "p2"], {"prompt_version": "poker-p2"})
    with pytest.raises(ValueError, match="Unknown prompt_version"):
        plugin.initial_state(["p1", "p2"], {"prompt_version": "werewolf-p2"})


def test_rules_and_summary_follow_the_chosen_version():
    plugin = Poker()
    request = requests_of(3)[0]

    assert plugin.rules() == prompt.rules_text("poker-p1")
    assert plugin.rules({"prompt_version": "poker-p2"}) == prompt.rules_text("poker-p2")
    assert plugin.situation_summary(request.observation) is None
    summary = plugin.situation_summary(request.observation, {"prompt_version": "poker-p2"})
    assert summary and f"You are {request.player}" in summary


def test_starting_hands_and_made_hands_are_put_in_words():
    assert prompt.starting_hand(["Kh", "Ks"]) == "a pocket pair of kings"
    assert prompt.starting_hand(["Ah", "Kh"]) == "ace-king suited, connected"
    assert prompt.starting_hand(["7c", "2d"]) == "7-2 offsuit, far apart"
    assert prompt.starting_hand(["Th", "8h"]) == "ten-8 suited, 1-gap"
    assert prompt.made_hand(["Kh", "Ks"], ["2c", "7d"]) == ""  # fewer than five cards
    assert prompt.made_hand(["Kh", "Ks"], ["2c", "7d", "9s"]) == "a pair of kings"
    assert prompt.made_hand(["Ah", "Kh"], ["2h", "7h", "9h"]) == "a flush"


def test_the_chance_against_random_hands_is_sensible_and_repeatable():
    aces = prompt.equity_vs_random(["Ah", "As"], [], 1, "x")
    junk = prompt.equity_vs_random(["7c", "2d"], [], 1, "x")
    nuts = prompt.equity_vs_random(["Ah", "Kh"], ["Qh", "Jh", "Th"], 2, "x")

    assert 0.8 < aces < 0.9 and 0.3 < junk < 0.4 and nuts == 1.0
    assert aces == prompt.equity_vs_random(["Ah", "As"], [], 1, "x")


def test_the_summary_prices_a_call_and_names_only_the_readers_cards():
    for seed in (1, 2, 3):
        for request in requests_of(seed, players=4):
            summary = prompt.situation_summary(request.observation)
            own, board = set(request.observation["your_cards"]), set(request.observation["board"])

            assert set(CARD.findall(summary)) <= own | board
            if request.observation["to_call"]:
                assert "break even" in summary


def test_the_summary_of_a_hand_made_situation():
    observation = {
        "you": "p1",
        "hand": 3,
        "blinds": {"small": 10, "big": 20, "double_after_hand": 10},
        "your_cards": ["Ah", "Kd"],
        "board": ["Qs", "7c", "2d"],
        "street": "flop",
        "pot": 100,
        "players": [
            {
                "id": "p1",
                "stack": 400,
                "bet": 0,
                "in_hand": True,
                "all_in": False,
                "position": "button",
            },
            {
                "id": "p2",
                "stack": 800,
                "bet": 50,
                "in_hand": True,
                "all_in": False,
                "position": "big_blind",
            },
            {"id": "p3", "stack": 0, "bet": 0, "in_hand": False, "all_in": False, "position": None},
        ],
        "your_turn": True,
        "to_call": 50,
        "min_raise_to": 100,
        "max_raise_to": 400,
    }

    summary = prompt.situation_summary(observation)

    assert "p1, button" in summary and "ace-king offsuit, connected" in summary
    assert "400 chips = 20.0 big blinds" in summary
    assert "50 into a pot of 100" in summary and "33%" in summary  # 50 / 150
    assert "between 100 and 400" in summary and "Against 1 random hand" in summary
    assert "p3" not in summary


def test_every_tool_of_every_turn_is_explained_in_the_rules_of_both_versions():
    for version in prompt.VERSIONS:
        rules = prompt.rules_text(version)
        for request in requests_of(5, players=4):
            for tool in request.tools:
                assert f"`{tool.name}(" in rules, (version, tool.name)


def test_the_summary_and_the_whole_prompt_stay_small():
    longest = 0
    for request in requests_of(6, players=4):
        summary = prompt.situation_summary(request.observation)
        messages = build_messages("Poker", prompt.rules_text("poker-p2"), request)
        longest = max(longest, sum(len(m["content"]) for m in messages) + len(summary))
        assert len(summary) < 1100
    assert longest < 16_000


def check_golden(name: str, text: str) -> None:
    path = GOLDEN / name
    GOLDEN.mkdir(exist_ok=True)
    if os.environ.get("UPDATE_GOLDEN"):
        path.write_text(text, encoding="utf-8", newline="\n")
    assert path.exists(), f"{name} is missing; run with UPDATE_GOLDEN=1"
    assert text == path.read_text(encoding="utf-8"), f"{name} changed; UPDATE_GOLDEN=1 if intended"


def a_request():
    return requests_of(7, players=3)[6]


def test_golden_prompt_of_version_p1_is_exactly_what_the_runner_builds_today():
    messages = build_messages("Poker", prompt.rules_text("poker-p1"), a_request())

    check_golden("poker-p1.txt", "\n=====\n".join(m["content"] for m in messages) + "\n")


def test_golden_prompt_of_version_p2_has_the_new_rules_and_the_summary():
    request = a_request()
    plugin = Poker()
    settings = {"prompt_version": "poker-p2"}
    summary = plugin.situation_summary(request.observation, settings)
    messages = build_messages("Poker", plugin.rules(settings), request, summary)

    check_golden("poker-p2.txt", "\n=====\n".join(m["content"] for m in messages) + "\n")
