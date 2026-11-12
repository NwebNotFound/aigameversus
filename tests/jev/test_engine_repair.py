"""answer_repair "v2" in a match: a still-broken call goes to Jev, only its legal pick plays."""

import asyncio
import json

import pytest

from arena.agents.mock_llm import MockLLM, tool_call
from arena.agents.random_bot import random_bots
from arena.agents.runner import ModelAgent
from arena.engine.match import Match
from arena.games import load_games
from arena.jev.client import FakeJev, JevError
from arena.jev.config import load_jev_config
from arena.jev.repair import JevRepairer
from games.toy.plugin import ToyGame

CONFIG = load_jev_config()
WHOLE = CONFIG.model_copy(update={"situation_chars": 1_000_000, "reasoning_chars": 1_000_000})
BROKEN = tool_call("play_cards", {"card": 3})  # no such tool: every correction is refused too


def sure(top=0.95):
    """A Jev that names its first option with this probability."""

    def answer(state, questions):
        options = list(questions["intended_move"]["criteria"])
        rest = (1 - top) / max(len(options) - 1, 1)
        probabilities = {name: (top if i == 0 else rest) for i, name in enumerate(options)}
        return {
            "answers": {
                "intended_move": {
                    "type": "choice",
                    "choice": options[0],
                    "probabilities": probabilities,
                }
            },
            "usage": {"input_tokens": 200, "cost": 0.000008},
        }

    return answer


def toy_match(repair, jev, seed=3):
    plugin = ToyGame()
    broken = MockLLM(*[BROKEN] * 60)
    agents = {"p1": ModelAgent(broken, plugin, settings={"answer_repair": repair})}
    agents |= random_bots(plugin, ["p2"], seed)
    repairer = JevRepairer(lambda player: jev, CONFIG) if jev is not None else None
    match = Match(plugin, agents, seed=seed, settings={"answer_repair": repair}, repairer=repairer)
    asyncio.run(match.run())
    return match.events


def of(events, type):
    return [e for e in events if e.type == type]


def test_v2_plays_jevs_legal_pick_and_marks_it_in_the_move_and_its_decision():
    jev = FakeJev(*[sure()] * 20)

    events = toy_match("v2", jev)

    repaired = [e for e in of(events, "action_accepted") if e.data.get("repaired_by") == "jev"]
    assert repaired and all(e.data["top_probability"] == 0.95 for e in repaired)
    assert of(events, "action_fallback") == []  # every broken move was repaired
    decisions = [e.data for e in of(events, "decision") if e.data["player"] == "p1"]
    assert all(d["jev"]["reason"] == "accepted" and d["fallback"] is None for d in decisions)
    assert len(jev.calls) == len(repaired)
    # The refused attempts are still in the log: the tool-error count does not change.
    assert len(of(events, "action_rejected")) == 3 * len(repaired)


def test_v1_and_off_never_ask_jev():
    for repair in ("off", "v1"):
        jev = FakeJev(*[sure()] * 20)
        events = toy_match(repair, jev)
        assert jev.calls == []
        assert of(events, "action_fallback")
        assert not any("jev" in e.data for e in of(events, "decision"))


@pytest.mark.parametrize(
    ("script", "reason"),
    [
        ((sure(0.6),), "below_threshold"),
        ((JevError("timeout"),), "timeout"),
        ((ValueError("boom"),), "error"),
    ],
)
def test_an_unsure_or_failing_jev_leaves_the_random_fallback_with_its_reason(script, reason):
    jev = FakeJev(*(list(script) * 20))

    events = toy_match("v2", jev)

    assert of(events, "action_fallback")
    assert not any(e.data.get("repaired_by") for e in of(events, "action_accepted"))
    decisions = [e.data for e in of(events, "decision") if e.data["player"] == "p1"]
    assert {d["jev"]["reason"] for d in decisions} == {reason}
    assert all(d["fallback"] == "rejected" for d in decisions)


def test_v2_without_a_repairer_plays_like_v1():
    events = toy_match("v2", None)

    assert of(events, "action_fallback")
    assert not any("jev" in e.data for e in of(events, "decision"))


def test_the_same_seed_gives_the_same_game_with_the_same_jev_answers():
    first = toy_match("v2", FakeJev(*[sure()] * 20))
    second = toy_match("v2", FakeJev(*[sure()] * 20))

    assert [(e.type, e.data) for e in first] == [(e.type, e.data) for e in second]


def test_jev_never_reads_what_the_repaired_player_may_not_see():
    plugin = load_games()["werewolf"]
    seats = [f"p{i}" for i in range(1, 9)]
    jev = FakeJev(*[sure()] * 200)
    broken = MockLLM(*[tool_call("no_such_tool", {})] * 2000)
    agents = random_bots(plugin, seats, 4)
    agents["p1"] = ModelAgent(broken, plugin, settings={"answer_repair": "v2"})
    match = Match(
        plugin,
        agents,
        seed=4,
        settings={"answer_repair": "v2"},
        # The whole situation, uncut: a leak anywhere in it must show.
        repairer=JevRepairer(lambda player: jev, WHOLE),
    )
    asyncio.run(match.run())

    roles = {e.data["player"]: e.data["role"] for e in match.events if e.type == "role_assigned"}
    wolves = {p for p, role in roles.items() if role in ("werewolf", "prime_wolf", "white_wolf")}
    died = {e.data["player"] for e in match.events if e.type == "player_died"}
    # Roles that stay hidden from p1 the whole match: alive at the end, and not p1's packmates.
    hidden = {
        p: r for p, r in roles.items() if p != "p1" and p not in died and not ({"p1", p} <= wolves)
    }
    assert jev.calls, "the broken seat was never repaired"
    assert hidden, "no role stayed hidden in this match: pick another seed"
    for state, questions in jev.calls:
        text = json.dumps(state).replace('\\"', '"')  # the situation is JSON in a string
        assert state["player"] == "p1"
        for player, role in hidden.items():
            assert f'"{player}": "{role}"' not in text, (player, role)
        # Options name legal moves only, never speech.
        assert not any(
            description.startswith(("speak(", "wolf_chat("))
            for description in questions["intended_move"]["criteria"].values()
        )


def test_the_report_counts_moves_repaired_by_jev_per_player():
    from arena.analytics import match_analytics

    plugin = load_games()["liars_deck"]
    jev = FakeJev(*[sure()] * 200)
    agents = random_bots(plugin, ["p1", "p2", "p3"], 2)
    agents["p1"] = ModelAgent(
        MockLLM(*[tool_call("no_such_tool", {})] * 500), plugin, settings={"answer_repair": "v2"}
    )
    match = Match(
        plugin,
        agents,
        seed=2,
        settings={"answer_repair": "v2"},
        repairer=JevRepairer(lambda player: jev, CONFIG),
    )
    asyncio.run(match.run())

    report = match_analytics("liars_deck", match.events, True)["report"]
    rows = {row["seat"]: {c["key"]: c["value"] for c in row["values"]} for row in report["ranking"]}
    assert rows["p1"]["jev_repaired"] == len(jev.calls) > 0
    assert rows["p2"]["jev_repaired"] == 0
    assert report["at_a_glance"]["jev_repaired"] == len(jev.calls)
    hidden = match_analytics("liars_deck", match.events, False)["report"]
    assert hidden["at_a_glance"]["jev_repaired"] is None  # spectators only
