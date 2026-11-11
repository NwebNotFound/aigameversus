"""The prompt of Werewolf: versions, summary, no leaks, every tool named, size, golden files."""

import asyncio
import os
import re
from pathlib import Path

import pytest

from arena.agents.prompt import build_messages
from arena.agents.random_bot import RandomBot
from arena.engine.match import Match
from arena.engine.rng import derive_rng
from games.werewolf import prompt
from games.werewolf.plugin import Werewolf
from games.werewolf.selection import load_roles

GOLDEN = Path(__file__).parent / "golden"
ROLES = load_roles()
ALL_ROLES = {"roles": dict.fromkeys(ROLES, 1)}  # every role once: 16 players
ALWAYS_NAMED = {"werewolf", "villager"}  # the goal text says "every werewolf" and "villagers"


class Spy(RandomBot):
    def __init__(self, plugin, rng, seen):
        super().__init__(plugin, rng)
        self.seen = seen

    async def act(self, request):
        self.seen.append(request)
        return await super().act(request)


def requests_of(seed, players=16, settings=None):
    plugin, seen = Werewolf(), []
    agents = {f"p{i}": Spy(plugin, derive_rng(seed, "spy", i), seen) for i in range(players)}
    asyncio.run(Match(plugin, agents, seed=seed, settings=settings or ALL_ROLES).run())
    return seen


def test_the_versions_are_p1_as_it_was_and_p2_with_new_rules():
    old = prompt.rules_text("werewolf-p1")
    new = prompt.rules_text("werewolf-p2")

    assert old == (Path(prompt.__file__).parent / "rules.md").read_text(encoding="utf-8")
    assert "How to play well" in new and "How to play well" not in old
    assert len(new.split()) < 1400


def test_the_prompt_version_is_a_setting_that_is_checked_and_reported():
    plugin = Werewolf()

    assert plugin.prompt_version({}) == "werewolf-p1"
    assert plugin.prompt_version({"prompt_version": "werewolf-p2"}) == "werewolf-p2"
    players = [f"p{i}" for i in range(8)]
    plugin.initial_state(players, {"prompt_version": "werewolf-p2"})
    with pytest.raises(ValueError, match="Unknown prompt_version"):
        plugin.initial_state(players, {"prompt_version": "poker-p2"})


def test_rules_and_summary_follow_the_chosen_version():
    plugin = Werewolf()
    request = requests_of(3)[0]
    settings = {"prompt_version": "werewolf-p2"}

    assert plugin.rules() == prompt.rules_text("werewolf-p1")
    assert plugin.rules(settings) == prompt.rules_text("werewolf-p2")
    assert plugin.situation_summary(request.observation) is None
    summary = plugin.situation_summary(request.observation, settings)
    assert summary and f"You are {request.player}" in summary


def test_the_summary_tells_only_what_the_reader_may_know():
    """Role ids appear only for the reader's own role, the dead, and the reader's own visions."""
    for seed in (1, 2, 3):
        for request in requests_of(seed):
            observation = request.observation
            summary = prompt.situation_summary(observation)
            allowed = set(ALWAYS_NAMED)
            allowed.add(observation["role"]["id"])
            allowed |= {d["role"] for d in observation["dead"]}
            allowed |= {r["role"] for r in observation["revealed_alive"]}
            allowed |= set(observation.get("seer_results", {}).values())
            for role_id in ROLES:
                if re.search(rf"\b{role_id}\b", summary):
                    assert role_id in allowed, (request.player, role_id, summary)
            if "pack" not in observation:
                assert "pack" not in summary.lower()


def test_the_summary_of_a_hand_made_situation():
    observation = {
        "you": "p2",
        "role": {"id": "seer", "name": "Seherin", "team": "village", "rules": ""},
        "phase": "day",
        "night": 2,
        "day": 2,
        "alive": ["p1", "p2", "p3", "p5"],
        "dead": [{"player": "p4", "role": "villager"}],
        "revealed_alive": [],
        "your_turn": True,
        "step": "vote",
        "speaking_order": ["p1", "p2", "p3", "p5"],
        "votes_today": {"p1": "p3", "p5": None},
        "captain": "p1",
        "language": "en",
        "seer_results": {"p3": "werewolf", "p1": "villager"},
    }

    assert prompt.situation_summary(observation) == "\n".join(
        [
            "You are p2, the Seherin (seer), team village. " + prompt.GOALS["village"],
            "It is day 2 (day). 4 alive: p1, p2, p3, p5.",
            "Dead: p4 was villager.",
            "Your visions: p3 is werewolf, p1 is villager.",
            "Captain: p1 (their vote counts double).",
            "Votes so far: p1 -> p3, p5 -> abstain.",
            "Your move now: vote. 3 other player(s) alive to choose from.",
        ]
    )


def test_every_tool_of_every_turn_is_explained_in_the_rules_of_both_versions():
    # the old rules never named `stay_in_bed` and `let_them_die`: that is why p2 exists
    for version in prompt.VERSIONS[1:]:
        rules = prompt.rules_text(version)
        for seed in range(1, 9):
            for request in requests_of(seed):
                for tool in request.tools:
                    assert f"`{tool.name}(" in rules, (version, tool.name)


def test_the_summary_and_the_whole_prompt_stay_small():
    longest = 0
    for request in requests_of(5):
        summary = prompt.situation_summary(request.observation)
        messages = build_messages("Werewolf", prompt.rules_text("werewolf-p2"), request)
        longest = max(longest, sum(len(m["content"]) for m in messages) + len(summary))
        assert len(summary) < 1500
    assert longest < 40_000


def check_golden(name: str, text: str) -> None:
    path = GOLDEN / name
    GOLDEN.mkdir(exist_ok=True)
    if os.environ.get("UPDATE_GOLDEN"):
        path.write_text(text, encoding="utf-8", newline="\n")
    assert path.exists(), f"{name} is missing; run with UPDATE_GOLDEN=1"
    assert text == path.read_text(encoding="utf-8"), f"{name} changed; UPDATE_GOLDEN=1 if intended"


def a_request():
    requests = requests_of(7, players=8, settings={"template": "classic"})
    return next(r for r in requests if r.observation["step"] == "vote")


def test_golden_prompt_of_version_p1_is_exactly_what_the_runner_builds_today():
    messages = build_messages("Werewolf", prompt.rules_text("werewolf-p1"), a_request())

    check_golden("werewolf-p1.txt", "\n=====\n".join(m["content"] for m in messages) + "\n")


def test_golden_prompt_of_version_p2_has_the_new_rules_and_the_summary():
    request = a_request()
    plugin = Werewolf()
    settings = {"prompt_version": "werewolf-p2"}
    summary = plugin.situation_summary(request.observation, settings)
    messages = build_messages("Werewolf", plugin.rules(settings), request, summary)

    check_golden("werewolf-p2.txt", "\n=====\n".join(m["content"] for m in messages) + "\n")
