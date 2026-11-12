"""The prompt of Throne of Tokens: versions, the three settings, the summary, golden files."""

import asyncio
import os
from collections import Counter
from pathlib import Path

import pytest

from arena.agents.prompt import build_messages
from arena.agents.random_bot import random_bots
from arena.engine.match import Match
from games.civ import prompt
from games.civ.plugin import CivGame

PLUGIN = CivGame()
GOLDEN = Path(__file__).parent / "golden"
FOUR = ["p1", "p2", "p3", "p4"]
SIX = [*FOUR, "p5", "p6"]


class Spy:
    """A random bot that keeps the requests it was asked."""

    def __init__(self, inner, seen):
        self.inner, self.seen = inner, seen

    async def act(self, request):
        self.seen.append(request)
        return await self.inner.act(request)


def requests_of(seed=3, players=FOUR, rounds=6, settings=None):
    seen: list = []
    bots = random_bots(PLUGIN, players, seed)
    agents = {p: Spy(bot, seen) for p, bot in bots.items()}
    asyncio.run(
        Match(PLUGIN, agents, seed=seed, settings={"rounds": rounds, **(settings or {})}).run()
    )
    return seen


def test_with_no_setting_the_rules_are_rules_md_and_there_is_no_summary():
    text = PLUGIN.rules({})

    assert text == prompt.base_rules()
    assert "## Think about the whole match" not in text and "## Your plan" not in text
    assert "your_plan_from_last_round" not in text
    assert PLUGIN.prompt_version({}) == "civ-p1"
    assert PLUGIN.situation_summary(requests_of()[0].observation, {}) is None


def test_each_setting_adds_its_own_section_and_nothing_else():
    base = prompt.base_rules()
    p2 = PLUGIN.rules({"prompt_version": "civ-p2"})
    strategy = PLUGIN.rules({"strategy_text": "v1"})
    plan = PLUGIN.rules({"private_plan": "on"})

    assert p2 == base + prompt.SUMMARY_GUIDE
    assert strategy == base + prompt.STRATEGY_V1
    assert plan == base + prompt.PLAN_ON
    both = PLUGIN.rules({"prompt_version": "civ-p2", "strategy_text": "v1", "private_plan": "on"})
    assert both == base + prompt.SUMMARY_GUIDE + prompt.PLAN_ON + prompt.STRATEGY_V1


def test_the_round_limit_setting_still_changes_the_rules_text():
    assert "After round 20," in PLUGIN.rules({"rounds": 20, "strategy_text": "v1"})


def test_the_strategy_text_has_no_quota_and_no_model_name():
    text = prompt.STRATEGY_V1.lower()

    assert not any(word in text for word in ("gpt", "claude", "gemma", "always", "at least once"))
    assert "whole match" in text and "thought" in text


@pytest.mark.parametrize(
    ("settings", "message"),
    [
        ({"prompt_version": "civ-p3"}, "Unknown prompt_version"),
        ({"strategy_text": "v2"}, "Unknown strategy_text"),
        ({"private_plan": True}, "Unknown private_plan"),
        ({"prompt_style": "x"}, "known: private_plan, prompt_version, rounds, strategy_text"),
    ],
)
def test_a_wrong_setting_is_refused_with_the_known_ones_named(settings, message):
    with pytest.raises(ValueError, match=message):
        PLUGIN.initial_state(FOUR, settings)


def test_the_settings_are_recorded_in_the_match_start():
    settings = {"prompt_version": "civ-p2", "strategy_text": "v1", "private_plan": "on"}
    match = Match(PLUGIN, random_bots(PLUGIN, FOUR, 1), seed=1, settings=settings | {"rounds": 2})
    asyncio.run(match.run())

    start = next(e for e in match.events if e.type == "match_started")
    assert start.data["settings"] == settings | {"rounds": 2}
    assert start.data["prompt_version"] == "civ-p2"


def test_the_plan_field_exists_only_when_the_plan_is_on():
    off = PLUGIN.get_tools(PLUGIN.initial_state(FOUR, {}), "p1")[0]
    on = PLUGIN.get_tools(PLUGIN.initial_state(FOUR, {"private_plan": "on"}), "p1")[0]

    assert "plan" not in off.parameters["properties"] and "`plan`" not in off.description
    assert "plan" in on.parameters["properties"]


def test_without_the_plan_setting_no_plan_is_kept_or_shown():
    for request in requests_of(settings={}):
        assert request.observation["your_plan_from_last_round"] is None


def test_every_tool_of_every_turn_is_named_in_the_rules_of_every_setting():
    for settings in ({}, {"prompt_version": "civ-p2", "private_plan": "on", "strategy_text": "v1"}):
        rules = PLUGIN.rules(settings)
        for request in requests_of(settings=settings):
            assert all(f"`{tool.name}`" in rules for tool in request.tools)


def test_the_summary_comes_from_the_observation_and_names_only_what_the_nation_sees():
    for request in requests_of(players=SIX, rounds=8):
        observation = request.observation
        summary = prompt.situation_summary(observation)
        seen_owners = {a["owner"] for a in observation["seen"]["armies"]}
        for other in (p for p in SIX if p != observation["you"]):
            if f"{other}'s" in summary:
                assert other in seen_owners  # only an army in sight is named
        assert summary.startswith(f"You are {observation['you']}. Round")
        assert len(summary) < 2500


def test_the_summary_says_what_was_refused_and_what_waits():
    request = requests_of()[-1]
    observation = request.observation | {
        "refused": [{"order": "build", "reason": "No free slot."}],
        "offers": [{"id": "o4", "from": "p2"}],
    }

    summary = prompt.situation_summary(observation)

    assert "Refused last round: build: No free slot." in summary
    assert "Offers waiting for your answer: o4 from p2." in summary


def test_the_prompt_stays_small_for_six_nations():
    longest = 0
    settings = {"prompt_version": "civ-p2", "strategy_text": "v1", "private_plan": "on"}
    for request in requests_of(players=SIX, rounds=20, settings=settings):
        summary = PLUGIN.situation_summary(request.observation, settings)
        messages = build_messages("Throne of Tokens", PLUGIN.rules(settings), request, summary)
        longest = max(longest, sum(len(m["content"]) for m in messages))
    assert longest < 60_000


def test_a_nation_sees_far_fewer_than_forty_events_a_round_in_bot_matches():
    """The prompt shows the last 40 visible events; bots stay well under it (talk will add)."""
    for players in (FOUR, SIX):
        seen: Counter = Counter()
        match = Match(PLUGIN, random_bots(PLUGIN, players, 3), seed=3, settings={"rounds": 20})
        asyncio.run(match.run())
        number = 0
        for event in match.events:
            if event.type == "round_started":
                number = event.data["round"]
            if event.source.value == "game":
                for player in players:
                    if event.is_visible_to(player):
                        seen[(player, number)] += 1
        assert max(seen.values()) < 30, max(seen.values())


def check_golden(name: str, text: str) -> None:
    path = GOLDEN / name
    GOLDEN.mkdir(exist_ok=True)
    if os.environ.get("UPDATE_GOLDEN"):
        path.write_text(text, encoding="utf-8", newline="\n")
    assert path.exists(), f"{name} is missing; run with UPDATE_GOLDEN=1"
    assert text == path.read_text(encoding="utf-8"), f"{name} changed; UPDATE_GOLDEN=1 if intended"


def a_request(settings):
    return requests_of(seed=7, players=FOUR, rounds=4, settings=settings)[len(FOUR) * 2]


@pytest.mark.parametrize(
    ("name", "settings"),
    [
        ("civ-p1.txt", {}),
        ("civ-p2.txt", {"prompt_version": "civ-p2"}),
        (
            "civ-p2-strategy-plan.txt",
            {"prompt_version": "civ-p2", "strategy_text": "v1", "private_plan": "on"},
        ),
    ],
)
def test_golden_prompts_of_the_versions(name, settings):
    settings = settings | {"rounds": 4}
    request = a_request(settings)
    summary = PLUGIN.situation_summary(request.observation, settings)
    messages = build_messages("Throne of Tokens", PLUGIN.rules(settings), request, summary)

    check_golden(name, "\n=====\n".join(m["content"] for m in messages) + "\n")
