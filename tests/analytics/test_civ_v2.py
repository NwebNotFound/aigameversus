"""civ/2: civ/1 plus per-round decisions and orders, treaty end rounds, and a report."""

import asyncio
import json
from pathlib import Path

import pytest

from arena.agents.random_bot import random_bots
from arena.analytics import UnknownVersion, match_analytics
from arena.engine.match import Match
from arena.engine.types import Event, EventSource
from games.civ.plugin import CivGame

GOLDEN = Path(__file__).parent / "golden" / "civ1_seed3.json"
NAMES = {"p1": "Bot 1", "p2": "Bot 2", "p3": "Bot 3", "p4": "Bot 4"}


def played(seed=3, rounds=10, players=4):
    plugin = CivGame()
    seats = [f"p{i}" for i in range(1, players + 1)]
    match = Match(plugin, random_bots(plugin, seats, seed), seed=seed, settings={"rounds": rounds})
    asyncio.run(match.run())
    return match.events


@pytest.fixture(scope="module")
def events():
    return played()


def as_json(value):
    return json.loads(json.dumps(value, sort_keys=True))


def test_civ_1_is_exactly_what_it_was_with_and_without_the_version_named(events):
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))

    for spoilers, key in ((True, "spoilers"), (False, "public")):
        assert as_json(match_analytics("civ", events, spoilers, {})) == golden[key]
        assert as_json(match_analytics("civ", events, spoilers, {}, "civ/1")) == golden[key]
    assert "report" not in golden["spoilers"]


def test_civ_2_is_civ_1_with_additions_only(events):
    one = match_analytics("civ", events, True, {})
    two = match_analytics("civ", events, True, {}, "civ/2")

    assert two["analytics_version"] == "civ/2" and one["analytics_version"] == "civ/1"
    for key in ("nations", "victory", "battles", "conquests", "orders", "decisions", "behaviour"):
        assert as_json(two[key]) == as_json(one[key])
    for p, nation in one["series"]["nations"].items():
        for key, values in nation.items():
            assert two["series"]["nations"][p][key] == values
    assert "report" in two and "report" not in one


def test_the_per_round_series_line_up_with_the_rounds(events):
    two = match_analytics("civ", events, True, {}, "civ/2")
    rounds = two["series"]["rounds"]

    for p, nation in two["series"]["nations"].items():
        assert len(nation["decisions"]) == len(nation["orders"]) == len(rounds)
        sent = sum(o["sent"] for o in nation["orders"])
        assert sent == two["orders"][p]["submitted"] + two["orders"][p]["by_fallback"]
        assert sum(o["dropped"] for o in nation["orders"]) == two["orders"][p]["dropped"]
        assert all(
            set(d)
            == {"latency_ms", "tokens_out", "reasoning_tokens", "cutoffs", "rejected", "fallback"}
            for d in nation["decisions"]
        )
        assert sum(d["rejected"] for d in nation["decisions"]) == two["decisions"][p]["rejected"]


def test_decisions_per_round_add_up_to_the_totals_of_a_model_match():
    def engine(type, data, player="p1"):
        return Event(
            source=EventSource.ENGINE, type=type, data={"player": player, **data}, visible_to=()
        )

    base = played(rounds=3)
    start = next(e for e in base if e.type == "match_started")
    marks = [i for i, e in enumerate(base) if e.type == "round_started"]
    log = list(base)
    # two decisions in round 1 (before the second round start), one in round 2
    for offset, (ms, out, cut) in enumerate([(900, 40, 1), (100, 10, 0)]):
        log.insert(
            marks[1] + offset,
            engine("decision", {"latency_ms": ms, "tokens_out": out, "cutoffs": cut}),
        )
    log.insert(
        marks[2] + 2, engine("decision", {"latency_ms": 50, "tokens_out": 5, "reasoning_tokens": 7})
    )
    assert start.data["players"][0] == "p1"

    two = match_analytics("civ", log, True, {}, "civ/2")
    rows = two["series"]["nations"]["p1"]["decisions"]

    assert rows[0]["latency_ms"] == 1000 and rows[0]["tokens_out"] == 50 and rows[0]["cutoffs"] == 1
    assert rows[1]["latency_ms"] == 50 and rows[1]["reasoning_tokens"] == 7
    assert two["decisions"]["p1"]["response_ms_total"] == 1050


def test_treaty_signed_has_its_end_round_and_a_break_says_how_early(events):
    def game(type, data):
        return Event(source=EventSource.GAME, type=type, data=data)

    log = list(events)
    last_round = max(e.data["round"] for e in log if e.type == "round_started")
    signed = game(
        "treaty_signed",
        {
            "treaty": "t9",
            "offer": "o9",
            "kind": "non_aggression",
            "parties": ["p1", "p2"],
            "ends_round": last_round + 5,
            "payer": None,
            "payment": {},
            "ends_war": False,
        },
    )
    broken = game("treaty_broken", {"treaty": "t9", "by": "p1", "on": "p2", "reputation": 30})
    open_ended = game(
        "treaty_signed",
        {
            "treaty": "t8",
            "offer": "o8",
            "kind": "peace",
            "parties": ["p3", "p4"],
            "ends_round": None,
            "payer": None,
            "payment": {},
            "ends_war": False,
        },
    )
    cut = next(i for i, e in enumerate(log) if e.type == "round_started" and e.data["round"] == 3)
    log[cut:cut] = [open_ended, signed, broken]

    items = {
        (i["event"], i["treaty"]): i
        for i in match_analytics("civ", log, True, {}, "civ/2")["diplomacy"]["timeline"]
        if "treaty" in i
    }
    assert items[("treaty_signed", "t9")]["until"] == last_round + 5
    assert items[("treaty_broken", "t9")]["rounds_early"] == last_round + 5 - 2 + 1
    assert items[("treaty_signed", "t8")]["until"] is None
    one = match_analytics("civ", log, True, {})["diplomacy"]["timeline"]
    assert all("until" not in i for i in one)  # civ/1 is untouched


def test_the_report_has_key_moments_one_turning_point_and_named_barbarians(events):
    report = match_analytics("civ", events, True, NAMES, "civ/2")["report"]
    moments = report["key_moments"]

    assert [m["seq"] for m in moments] == sorted(m["seq"] for m in moments)
    assert all(
        set(m) >= {"seq", "kind", "players", "importance", "text"}
        and set(m["text"]) == {"en", "de"}
        for m in moments
    )
    assert sum(1 for m in moments if m.get("turning")) <= 1
    point = report["at_a_glance"]["turning_point"]
    assert point is None or point["seq"] in {m["seq"] for m in moments}
    text = " ".join(m["text"]["en"] + m["text"]["de"] for m in moments)
    assert "neutral" not in text and "p1" not in text
    assert report["at_a_glance"]["over"] is True
    assert {c["key"] for c in report["columns"]} >= {"score", "cities_taken", "battles_won"}
    assert [r["seat"] for r in report["ranking"]]


def test_without_spoilers_the_report_has_only_public_moments_and_null_series(events):
    two = match_analytics("civ", events, False, NAMES, "civ/2")

    assert two["series"] is None and two["battles"] is None and two["orders"] is None
    kinds = {m["kind"] for m in two["report"]["key_moments"]}
    assert kinds <= {"betrayal", "war", "conquest", "victory"}  # no battle, no lead from the series
    row = two["report"]["ranking"][0]["values"]
    assert {v["key"]: v["value"] for v in row}["cities"] is None
    assert {v["key"]: v["value"] for v in row}["battles_won"] is None


def test_the_turning_point_is_where_the_winner_took_the_lead_for_good(events):
    two = match_analytics("civ", events, True, NAMES, "civ/2")
    winner = two["victory"]["winners"][0]
    nations, rounds = two["series"]["nations"], two["series"]["rounds"]
    seats = list(nations)
    lead = [
        max(seats, key=lambda p: (nations[p]["score"][i], -seats.index(p)))
        for i in range(len(rounds))
    ]
    behind = [i for i, p in enumerate(lead) if p != winner]
    turning = [m for m in two["report"]["key_moments"] if m.get("turning")]

    if behind and behind[-1] + 1 < len(rounds):
        turn = rounds[behind[-1] + 1]
        assert len(turning) == 1 and turning[0]["round"] in (turn - 1, turn)
    else:  # the winner led from the start (or ties): no lead change to point at
        assert len(turning) <= 1


def test_other_games_take_no_version_and_civ_refuses_an_unknown_one(events):
    with pytest.raises(UnknownVersion, match="civ/9"):
        match_analytics("civ", events, True, {}, "civ/9")
    with pytest.raises(UnknownVersion, match="one analytics version"):
        match_analytics("poker", events, True, {}, "poker/2")


def test_an_open_ended_treaty_that_is_broken_has_both_keys_set_to_null(events):
    def game(type, data):
        return Event(source=EventSource.GAME, type=type, data=data)

    log = list(events)
    cut = next(i for i, e in enumerate(log) if e.type == "round_started" and e.data["round"] == 3)
    signed = game(
        "treaty_signed",
        {
            "treaty": "t8",
            "offer": "o8",
            "kind": "peace",
            "parties": ["p3", "p4"],
            "ends_round": None,
            "payer": None,
            "payment": {},
            "ends_war": False,
        },
    )
    broken = game("treaty_broken", {"treaty": "t8", "by": "p3", "on": "p4", "reputation": 30})
    unseen = game("treaty_broken", {"treaty": "t7", "by": "p1", "on": "p2", "reputation": 30})
    log[cut:cut] = [signed, broken, unseen]

    items = {
        (i["event"], i["treaty"]): i
        for i in match_analytics("civ", log, True, {}, "civ/2")["diplomacy"]["timeline"]
        if "treaty" in i
    }
    assert items[("treaty_broken", "t8")]["until"] is None
    assert items[("treaty_broken", "t8")]["rounds_early"] is None
    # a break whose signing is not in the log: the keys are there, unknown
    assert items[("treaty_broken", "t7")]["until"] is None
    assert items[("treaty_broken", "t7")]["rounds_early"] is None


def test_private_events_never_reach_the_spoiler_free_civ_2_answer(events):
    def private(type, data):
        return Event(source=EventSource.GAME, type=type, data=data, visible_to=["p1"])

    marker = "SECRETMARK77"
    log = list(events)
    cut = next(i for i, e in enumerate(log) if e.type == "round_started" and e.data["round"] == 3)
    injected = [
        private(
            "war_declared",
            {"by": "p1", "on": "p2", "reputation": 20, "joined": [], "broken": [], "note": marker},
        ),
        private(
            "treaty_signed",
            {
                "treaty": marker,
                "offer": "o77",
                "kind": "peace",
                "parties": ["p1", "p2"],
                "ends_round": 9,
                "payer": None,
                "payment": {},
                "ends_war": False,
            },
        ),
        private("treaty_broken", {"treaty": marker, "by": "p1", "on": "p2", "reputation": 10}),
    ]
    log[cut:cut] = injected

    public = match_analytics("civ", log, False, NAMES, "civ/2")
    base = match_analytics("civ", events, False, NAMES, "civ/2")
    full = match_analytics("civ", log, True, NAMES, "civ/2")

    assert marker not in json.dumps(public)
    assert (
        public["diplomacy"]["by_nation"]["p1"]["wars_declared"]
        == (base["diplomacy"]["by_nation"]["p1"]["wars_declared"])
    )
    assert [m["text"] for m in public["report"]["key_moments"]] == [
        m["text"] for m in base["report"]["key_moments"]
    ]
    assert marker in json.dumps(full)  # the same log with spoilers does hold it
