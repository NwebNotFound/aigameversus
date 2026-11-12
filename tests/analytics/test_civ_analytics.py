"""Throne of Tokens analytics, from seeded bot matches, scripted diplomacy and a mock model."""

import asyncio
import json
from functools import cache
from pathlib import Path

import games.civ.tests
from arena.agents.mock_llm import MockLLM, tool_call
from arena.agents.model import Usage
from arena.agents.random_bot import random_bots
from arena.agents.runner import ModelAgent
from arena.analytics import civ, match_analytics
from arena.engine.match import Match
from arena.engine.types import Action, Event, Reply
from games.civ.plugin import CivGame

PLUGIN = CivGame()
FOUR = ["p1", "p2", "p3", "p4"]
BATTLES_SEED = 3  # a 20-round bot match with barbarian battles and conquests


def play(seed=BATTLES_SEED, agents=None, rounds=20) -> Match:
    seats = random_bots(PLUGIN, FOUR, seed) | (agents or {})
    match = Match(PLUGIN, seats, seed=seed, settings={"rounds": rounds})
    asyncio.run(match.run())
    return match


@cache
def bot_match() -> Match:
    return play()


def of_type(match, kind):
    return [e for e in match.events if e.type == kind]


def test_a_bot_match_gives_every_section_with_spoilers_and_its_numbers_agree_with_the_log():
    match = bot_match()

    found = match_analytics("civ", match.events, True)

    assert found["analytics_version"] == civ.VERSION and found["nations"] == FOUR
    for section in ("series", "victory", "battles", "conquests", "diplomacy", "orders"):
        assert section in found["sections"]
    series = found["series"]
    assert series["rounds"] == list(range(1, match.state.round + 1))
    standings = {s["player"]: s["score"] for s in found["victory"]["standings"]}
    for nation in FOUR:
        assert series["nations"][nation]["score"][-1] == standings[nation]
        cities = sum(1 for c in match.state.cities if c.owner == nation)
        assert series["nations"][nation]["cities"][-1] == cities
        assert len(series["nations"][nation]["stock"]) == len(series["rounds"])
    assert len(found["battles"]) == len(of_type(match, "battle")) > 0
    assert len(found["conquests"]) == len(of_type(match, "city_conquered")) > 0
    sent = sum(
        len(e.data["arguments"]["orders"])
        for e in of_type(match, "action_accepted")
        if e.data["player"] == "p1"
    )
    refused = [e for e in of_type(match, "order_refused") if e.data["nation"] == "p1"]
    assert found["orders"]["p1"]["submitted"] == sent
    assert found["orders"]["p1"]["dropped"] == len(refused)
    assert found["victory"]["kind"] == match.state.victory["kind"]


def test_without_spoilers_only_public_parts_remain_and_private_events_change_nothing():
    match = bot_match()

    free = match_analytics("civ", match.events, False)
    for hidden in ("series", "battles", "orders", "decisions", "behaviour"):
        assert free[hidden] is None
    assert free["conquests"] == match_analytics("civ", match.events, True)["conquests"]
    assert free["diplomacy"]["by_nation"]["p1"]["offers_sent"] is None

    changed = [
        e.model_copy(update={"data": {**e.data, "yields": {"gold": 999}}})
        if e.type == "production"
        else e
        for e in match.events
    ]
    assert match_analytics("civ", changed, False) == free


def test_the_same_log_gives_the_same_answer():
    match = bot_match()

    assert match_analytics("civ", match.events, True) == match_analytics("civ", match.events, True)


class Scripted:
    """A nation that plays a fixed call per round (round numbers from its observation)."""

    def __init__(self, script):
        self.script = script

    async def act(self, request):
        orders = self.script(request.observation)
        return Reply(action=Action(tool="submit_orders", arguments={"orders": orders}))


def test_diplomacy_and_behaviour_tags_follow_the_orders():
    def p1(seen):
        rounds = {
            1: [
                {"type": "propose_treaty", "to": "p2", "kind": "non_aggression", "rounds": 10},
                {"type": "propose_trade", "to": "p2", "gives": {"wood": 1}, "wants": {}},
            ],
            2: [{"type": "propose_trade", "to": "p2", "gives": {"wood": 1}, "wants": {}}],
            4: [{"type": "declare_war", "on": "p2"}],
        }
        return rounds.get(seen["round"], [])

    def p2(seen):
        return [{"type": "respond", "offer": o["id"], "accept": True} for o in seen["offers"]]

    match = play(seed=2, agents={"p1": Scripted(p1), "p2": Scripted(p2)}, rounds=6)
    found = match_analytics("civ", match.events, True)

    p1_dip = found["diplomacy"]["by_nation"]["p1"]
    assert (p1_dip["offers_sent"], p1_dip["wars_declared"]) == (3, 1)
    assert found["diplomacy"]["by_nation"]["p2"]["offers_accepted"] == 3
    events = [item["event"] for item in found["diplomacy"]["timeline"]]
    assert events.index("treaty_signed") < events.index("war_declared")
    war = next(i for i in found["diplomacy"]["timeline"] if i["event"] == "war_declared")
    assert war["by"] == "p1" and war["on"] == "p2" and war["broken"]
    assert {"aggressor", "betrayer", "trader"} <= set(found["behaviour"]["p1"]["tags"])
    assert "trader" in found["behaviour"]["p2"]["tags"]
    assert found["series"]["nations"]["p1"]["at_war"][-1] == ["p2"]
    free = match_analytics("civ", match.events, False)
    assert free["diplomacy"]["by_nation"]["p1"]["wars_declared"] == 1  # public


def test_a_model_seat_has_decision_numbers_and_a_bot_has_none():
    answer = tool_call("submit_orders", {"orders": []}, usage=Usage(1000, 50, 10))
    agent = ModelAgent(MockLLM(answer), PLUGIN)

    found = match_analytics("civ", play(seed=5, agents={"p1": agent}, rounds=5).events, True)

    model, bot = found["decisions"]["p1"], found["decisions"]["p2"]
    assert model["model_moves"] == model["moves"] == 5
    assert (model["tokens_in"], model["tokens_out"]) == (5000, 250)
    assert bot["model_moves"] == 0 and bot["tokens_in"] is None


def test_a_refusal_counts_by_its_kind_not_by_its_ids():
    assert civ.reason_kind("You have no army 'a12'. Your armies: a3, a7.") == civ.reason_kind(
        "You have no army 'a4'. Your armies: a1."
    )
    assert civ.reason_kind("a3 cannot reach (4, 7) this round.") == "# cannot reach # this round."


def test_a_match_of_an_older_rules_version_is_analysed_with_its_own_rules():
    golden = json.loads(
        (Path(games.civ.tests.__file__).parent / "golden" / "v1_match.json").read_text("utf-8")
    )
    events = [Event(**event) for event in golden["events"]]

    found = match_analytics("civ", events, True)

    assert found["meta"]["version"] == "1"
    final = golden["final_state"]
    for nation in golden["players"]:
        cities = sum(1 for c in final["cities"] if c["owner"] == nation)
        assert found["series"]["nations"][nation]["cities"][-1] == cities
        assert found["series"]["nations"][nation]["stock"][-1] == final["nations"][nation]["stock"]
