"""The prompt of Liar's Deck: versions, summary, no leaks, every tool named, size, golden files."""

import asyncio
import os
import re
from pathlib import Path

import pytest

from arena.agents.prompt import build_messages
from arena.agents.random_bot import RandomBot
from arena.engine.match import Match
from arena.engine.rng import derive_rng
from arena.engine.types import Event, TurnRequest
from games.liars_deck import prompt
from games.liars_deck.plugin import LiarsDeck

GOLDEN = Path(__file__).parent / "golden"
CARD = re.compile(r"\b(?:[KQA][1-6]|J[12]|DV)\b")


class Spy(RandomBot):
    """A random bot that keeps every request it was asked."""

    def __init__(self, plugin, rng, seen):
        super().__init__(plugin, rng)
        self.seen = seen

    async def act(self, request):
        self.seen.append(request)
        return await super().act(request)


def requests_of(seed, players=3, settings=None):
    plugin, seen = LiarsDeck(), []
    agents = {f"p{i}": Spy(plugin, derive_rng(seed, "spy", i), seen) for i in range(1, players + 1)}
    asyncio.run(Match(plugin, agents, seed=seed, settings=settings or {}).run())
    return seen


def test_the_versions_are_p1_as_it_was_and_p2_with_new_rules():
    old = prompt.rules_text("liars_deck-p1")
    new = prompt.rules_text("liars_deck-p2")

    assert old == (Path(prompt.__file__).parent / "rules.md").read_text(encoding="utf-8")
    assert "How to play well" in new and "How to play well" not in old
    assert len(new.split()) < 1000


def test_the_prompt_version_is_a_setting_that_is_checked_and_reported():
    plugin = LiarsDeck()

    assert plugin.prompt_version({}) == "liars_deck-p1"
    assert plugin.prompt_version({"prompt_version": "liars_deck-p2"}) == "liars_deck-p2"
    plugin.initial_state(["p1", "p2"], {"prompt_version": "liars_deck-p2"})
    with pytest.raises(ValueError, match="Unknown prompt_version"):
        plugin.initial_state(["p1", "p2"], {"prompt_version": "poker-p2"})


def test_rules_and_summary_follow_the_chosen_version():
    plugin = LiarsDeck()
    request = requests_of(3)[0]

    assert plugin.rules() == prompt.rules_text("liars_deck-p1")
    assert plugin.rules({"prompt_version": "liars_deck-p2"}) == prompt.rules_text("liars_deck-p2")
    assert plugin.situation_summary(request.observation) is None
    summary = plugin.situation_summary(request.observation, {"prompt_version": "liars_deck-p2"})
    assert summary and f"You are {request.player}" in summary


def test_chances_match_the_table_in_the_rules():
    # Holding no true cards: 1, 2 and 3 unseen cards are all true with 53%, 27% and 12%.
    assert [round(prompt.chance_all_true(k, 0, 5) * 100) for k in (1, 2, 3)] == [53, 27, 12]
    assert [round(prompt.chance_all_true(k, 2, 5) * 100) for k in (1, 2, 3)] == [40, 14, 4]
    assert prompt.chance_all_true(3, 6, 5) == 0.0  # no such number of true cards left
    text = prompt.rules_text("liars_deck-p2")
    assert "| 0 | 53% | 27% | 12% |" in text and "| 4 | 27% | 6% | 1% |" in text


@pytest.mark.parametrize("variant", ["base", "devil_card"])
def test_the_summary_names_only_cards_of_the_reader(variant):
    for seed in (1, 2, 3, 4):
        for request in requests_of(seed, players=4, settings={"variant": variant}):
            summary = prompt.situation_summary(request.observation)

            assert set(CARD.findall(summary)) <= set(request.observation["hand"])


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
        messages = build_messages("Liar's Deck", prompt.rules_text("liars_deck-p2"), request)
        longest = max(longest, sum(len(m["content"]) for m in messages) + len(summary))
        assert len(summary) < 900
    assert longest < 14_000


def test_the_summary_says_what_a_last_play_means_for_the_reader():
    plugin = LiarsDeck()
    observation = {
        "you": "p1",
        "table_card": "queen",
        "round": 2,
        "hand": ["Q1", "J1", "K2", "A3", "A4"],
        "players": [
            {"id": "p1", "alive": True, "cards": 5, "trigger_pulls": 1, "chambers": 6},
            {"id": "p2", "alive": True, "cards": 3, "trigger_pulls": 3, "chambers": 6},
            {"id": "p3", "alive": False, "cards": 0, "trigger_pulls": 2, "chambers": 6},
        ],
        "last_play": {"player": "p2", "count": 2},
    }

    summary = plugin.situation_summary(observation, {"prompt_version": "liars_deck-p2"})

    assert "Cards that count as a queen: Q1 J1 (2)." in summary
    assert "risk is 1/5" in summary  # one pull behind you
    assert "p2 put down 2 card(s)" in summary and "14%" in summary
    assert "p2 3 card(s), next shot 1/3" in summary and "p3" not in summary.split("Others alive")[1]


# --- golden files -------------------------------------------------------------------


def check_golden(name: str, text: str) -> None:
    path = GOLDEN / name
    GOLDEN.mkdir(exist_ok=True)
    if os.environ.get("UPDATE_GOLDEN"):
        path.write_text(text, encoding="utf-8", newline="\n")
    assert path.exists(), f"{name} is missing; run with UPDATE_GOLDEN=1"
    assert text == path.read_text(encoding="utf-8"), f"{name} changed; UPDATE_GOLDEN=1 if intended"


def a_request():
    """The fifth turn of a seeded match, with its events, as the runner would ask it."""
    return requests_of(7, players=3)[4]


def test_golden_prompt_of_version_p1_is_exactly_what_the_runner_builds_today():
    request = a_request()
    messages = build_messages("Liar's Deck", prompt.rules_text("liars_deck-p1"), request)

    check_golden("liars_deck-p1.txt", "\n=====\n".join(m["content"] for m in messages) + "\n")


def test_golden_prompt_of_version_p2_has_the_new_rules_and_the_summary():
    request = a_request()
    plugin = LiarsDeck()
    settings = {"prompt_version": "liars_deck-p2"}
    messages = build_messages("Liar's Deck", plugin.rules(settings), request)
    summary = plugin.situation_summary(request.observation, settings)

    text = "\n=====\n".join(m["content"] for m in messages)
    check_golden("liars_deck-p2.txt", f"{text}\n=====\n<summary>\n{summary}\n</summary>\n")


def test_golden_requests_are_stable_for_a_seed():
    first = requests_of(7, players=3)[4]
    again = requests_of(7, players=3)[4]

    assert first.observation == again.observation
    assert isinstance(first, TurnRequest) and isinstance(first.events[0], Event)
