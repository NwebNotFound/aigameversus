"""Behaviour tags: each at, below and above its threshold, at n just under the minimum, per view."""

import asyncio

import pytest

from arena.agents.random_bot import random_bots
from arena.analytics import behaviour as b
from arena.analytics import match_analytics
from arena.analytics.liars_deck import rate
from arena.engine.match import Match
from arena.games import load_games


def move(player="p1", kind="play", **changes):
    return {
        "player": player,
        "kind": kind,
        "fallback": False,
        "automatic": False,
        "rejected": 0,
        "latency_ms": None,
        "honest": True,
        "risk": 0.0,
        **changes,
    }


def totals(**changes):
    base = {
        "chosen_lie_rate": rate(0, 0),
        "call_rate": rate(0, 0),
        "call_accuracy": rate(0, 0),
        "hit_rate": rate(0, 0),
        "false_alarm_rate": rate(0, 0),
        "fallback_share": rate(0, 0),
    }
    return {**base, **changes}


def tags(analytics, spoilers=True, player="p1"):
    found = b.liars_deck(analytics, spoilers, {})[player]["tags"]
    return {tag["id"]: tag for tag in found}


def table(p1_totals, moves=None, p2_totals=None):
    moves = moves if moves is not None else [move() for _ in range(12)]
    return {
        "players": ["p1", "p2"],
        "totals": {"p1": p1_totals, "p2": p2_totals or totals()},
        "moves": moves,
    }


def test_wilson_interval_matches_the_textbook_values():
    low, high = b.wilson(7, 10)
    assert (round(low, 3), round(high, 3)) == (0.397, 0.892)
    assert b.wilson(0, 0) is None
    assert b.wilson(0, 10)[0] == 0.0 and b.wilson(10, 10)[1] == 1.0


@pytest.mark.parametrize(
    ("lies", "plays", "tagged"),
    [
        (7, 10, False),  # 70 % but the interval reaches below 0.5: not yet
        (25, 35, True),  # 71 % with the interval above 0.5
        (9, 9, False),  # n just under the minimum
        (18, 36, False),  # exactly at the threshold
    ],
)
def test_bluffer_needs_the_whole_interval_above_one_half(lies, plays, tagged):
    found = tags(table(totals(chosen_lie_rate=rate(lies, plays))))
    assert ("bluffer" in found) is tagged
    if tagged:
        assert found["bluffer"]["text"]["en"].startswith(
            "lies in 71 % of plays with an honest card in hand (95 %: 55-84 %, n=35)"
        )
        assert found["bluffer"]["spoilers"] is True


@pytest.mark.parametrize(
    ("lies", "plays", "tagged"), [(0, 30, True), (1, 10, False), (3, 20, False)]
)
def test_honest_needs_the_whole_interval_below_the_threshold(lies, plays, tagged):
    assert ("honest" in tags(table(totals(chosen_lie_rate=rate(lies, plays))))) is tagged


def test_tags_from_hidden_cards_or_private_events_need_spoilers():
    analytics = table(
        totals(
            chosen_lie_rate=rate(30, 35),
            fallback_share=rate(5, 20),
            hit_rate=rate(9, 10),
            false_alarm_rate=rate(0, 20),
        ),
        moves=[move(rejected=1, honest=False, risk=0.5) for _ in range(12)],
    )

    assert {"bluffer", "sharp_eye", "risk_taker", "rule_breaker", "replaced"} <= set(
        tags(analytics)
    )
    assert set(tags(analytics, spoilers=False)) == set()


@pytest.mark.parametrize(
    ("calls", "chances", "tag"),
    [(0, 30, "cautious"), (1, 10, None), (25, 30, "trigger_happy"), (6, 10, None), (5, 9, None)],
)
def test_call_rate_tags_are_public_and_need_a_clear_interval(calls, chances, tag):
    found = tags(table(totals(call_rate=rate(calls, chances))), spoilers=False)
    assert set(found) == ({tag} if tag else set())


@pytest.mark.parametrize(
    ("hits", "alarms", "tagged"),
    [((9, 10), (1, 20), True), ((5, 10), (3, 10), False), ((9, 9), (0, 20), False)],
)
def test_sharp_eye_needs_a_gap_of_point_two_and_no_overlap(hits, alarms, tagged):
    found = tags(table(totals(hit_rate=rate(*hits), false_alarm_rate=rate(*alarms))))
    assert ("sharp_eye" in found) is tagged


@pytest.mark.parametrize(
    ("risky_lies", "risky_honest", "plays", "tagged"),
    [
        (3, 1, 10, True),  # 3 of 4 risky plays were lies
        (3, 3, 10, True),  # exactly half
        (3, 4, 10, False),  # often at risk, lies rarely there: not a risk-taker
        (2, 0, 12, False),  # under 3 risky lies
        (3, 0, 9, False),  # n just under the minimum
    ],
)
def test_risk_taker_lies_at_a_third_or_more_three_times_and_half_the_time(
    risky_lies, risky_honest, plays, tagged
):
    moves = [move(honest=False, risk=0.33) for _ in range(risky_lies)]
    moves += [move(honest=True, risk=0.5) for _ in range(risky_honest)]
    moves += [move(honest=False, risk=0.2) for _ in range(plays - risky_lies - risky_honest)]
    found = tags(table(totals(), moves))
    assert ("risk_taker" in found) is tagged
    if tagged and risky_honest == 1:
        assert found["risk_taker"]["text"]["en"] == (
            "lied 3 of the 4 times it played at a 33 % or higher chance that the next pull fires"
        )


@pytest.mark.parametrize(
    ("refused", "moves", "tagged"), [(3, 10, True), (5, 20, False), (9, 9, False)]
)
def test_rule_breaker_refused_answers_per_move_above_a_quarter(refused, moves, tagged):
    made = [move(rejected=1 if i < refused else 0) for i in range(moves)]
    assert ("rule_breaker" in tags(table(totals(), made))) is tagged


def test_fallback_moves_never_count_as_own_decisions():
    moves = [move(rejected=1, fallback=True) for _ in range(20)] + [move() for _ in range(5)]

    result = b.liars_deck(table(totals(), moves), True, {})["p1"]

    assert "rule_breaker" not in {t["id"] for t in result["tags"]}
    assert result["too_early"] == {"n": 5, "need": 10}


@pytest.mark.parametrize(("bot", "moves", "tagged"), [(3, 20, True), (2, 20, False), (2, 9, False)])
def test_often_replaced_by_the_bot_is_a_reliability_tag(bot, moves, tagged):
    found = tags(table(totals(fallback_share=rate(bot, moves))))
    assert ("replaced" in found) is tagged
    if tagged:
        assert found["replaced"]["kind"] == "reliability"


@pytest.mark.parametrize(
    ("mine", "others", "tag"),
    [(5000, 2000, "slow"), (900, 2000, "quick"), (3000, 2000, None), (4000, 2000, None)],
)
def test_speed_is_relative_to_the_other_seats_and_says_answer(mine, others, tag):
    moves = [move(latency_ms=mine) for _ in range(10)]
    moves += [move(player="p2", latency_ms=others) for _ in range(10)]
    found = tags(table(totals(), moves), spoilers=False)
    assert set(found) == ({tag} if tag else set())
    if tag:
        assert "to answer" in found[tag]["label"]["en"].lower()
        assert "includes the network" in found[tag]["text"]["en"]


def test_compare_says_above_below_or_about_only_with_enough_on_both_sides():
    analytics = table(
        totals(call_rate=rate(25, 30), call_accuracy=rate(3, 6)),
        p2_totals=totals(call_rate=rate(3, 30), call_accuracy=rate(5, 10)),
    )

    compare = b.liars_deck(analytics, False, {})
    assert compare["p1"]["compare"] == {"call_rate": "above", "call_accuracy": "too few"}
    assert compare["p2"]["compare"]["call_rate"] == "below"


def test_the_last_thought_is_shown_only_to_spectators_and_cut_short():
    long = "I think " * 60
    result = b.liars_deck(table(totals()), True, {"p1": long})
    assert result["p1"]["last_thought"].endswith("…")
    assert len(result["p1"]["last_thought"]) == b.THOUGHT_CHARS
    assert "last_thought" not in b.liars_deck(table(totals()), False, {"p1": long})["p1"]


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_a_bot_match_gets_behaviour_for_every_player_in_both_views(seed):
    plugin = load_games()["liars_deck"]
    seats = ["p1", "p2", "p3", "p4"]
    match = Match(plugin, random_bots(plugin, seats, seed), seed=seed)
    asyncio.run(match.run())

    for spoilers in (True, False):
        found = match_analytics("liars_deck", match.events, spoilers)["behaviour"]
        assert set(found) == set(seats)
        for player in found.values():
            assert all(not tag["spoilers"] or spoilers for tag in player["tags"])
