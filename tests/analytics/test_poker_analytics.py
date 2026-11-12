"""Poker analytics: hands, moves, chips and the rates, from public events; hole-card numbers only
with spoilers."""

import asyncio
import json

import pytest

from arena.agents.random_bot import random_bots
from arena.analytics import match_analytics
from arena.engine.match import Match
from arena.engine.types import Event, EventSource
from arena.stats import poker as stats
from games.poker.plugin import Poker

# null without spoilers: they read hole cards, or the engine events that are spectators only
SECRET = ("bluff_hands", "bluff_rate", "worst_decisions", "fallbacks", "refused")


def played(players=3, seed=3, settings=None):
    plugin = Poker()
    seats = random_bots(plugin, [f"p{i}" for i in range(1, players + 1)], seed)
    match = Match(plugin, seats, seed=seed, settings=settings or {})
    asyncio.run(match.run())
    return match.events


@pytest.fixture(scope="module", params=[(2, 1), (3, 3), (4, 5)], ids=["2p", "3p", "4p"])
def match(request):
    players, seed = request.param
    return players, played(players, seed)


def test_the_chips_series_ends_where_the_hands_left_them_and_all_chips_stay_in_play(match):
    players, events = match
    a = match_analytics("poker", events, True)

    assert a["numbers"] is True
    assert all(len(series) == len(a["hands"]) + 1 for series in a["chips"].values())
    assert sum(series[-1] for series in a["chips"].values()) == players * 1000
    for player, totals in a["totals"].items():
        assert totals["net_chips"] == a["chips"][player][-1] - 1000
        assert totals["final_chips"] == a["chips"][player][-1]
    assert [h["hand"] for h in a["hands"]] == list(range(1, len(a["hands"]) + 1))
    assert all(sum(h["net"].values()) == 0 for h in a["hands"])  # a pot is zero-sum
    assert all(sum(h["winners"].values()) == h["pot"] for h in a["hands"])


def test_every_bet_action_is_one_move_and_the_kinds_add_up(match):
    _, events = match
    a = match_analytics("poker", events, True)

    assert len(a["moves"]) == sum(1 for e in events if e.type == "bet_action")
    for player, totals in a["totals"].items():
        mine = [m for m in a["moves"] if m["player"] == player]
        assert totals["moves"] == len(mine)
        kinds = totals["folds"] + totals["checks"] + totals["calls"] + totals["raises"]
        assert kinds + totals["all_ins"] == len(mine)
        assert totals["fold_rate"]["n"] == totals["folds"]


def test_vpip_and_aggression_are_the_definitions_of_the_profile_statistics(match):
    _, events = match
    a = match_analytics("poker", events, True)
    expected = stats.match_stats(events)

    for player, totals in a["totals"].items():
        mine = expected[player]
        assert totals["hands"] == mine.hands
        assert totals["net_chips"] == mine.net_chips
        assert totals["aggressive_actions"] == mine.aggressive_actions
        assert totals["vpip"]["n"] == mine.vpip_hands
        assert totals["bluff_hands"] == mine.bluff_hands
        assert totals["worst_decisions"] == mine.worst_decisions
        if mine.calls:
            assert totals["aggression_factor"] == mine.aggressive_actions / mine.calls


def test_without_spoilers_only_the_hole_card_numbers_are_missing(match):
    _, events = match
    full = match_analytics("poker", events, True)
    public = match_analytics("poker", events, False)

    for player in full["players"]:
        for key, value in full["totals"][player].items():
            if key in SECRET:
                assert public["totals"][player][key] is None
            else:
                assert public["totals"][player][key] == value, key
    assert public["chips"] == full["chips"] and public["hands"] == full["hands"]


def test_no_hole_card_of_a_hand_nobody_showed_is_in_the_public_answer(match):
    _, events = match
    shown = {c for e in events if e.type == "showdown" for h in e.data["hands"] for c in h["cards"]}
    board = {c for e in events if e.type == "street_started" for c in e.data["cards"]}
    secret = {
        c for e in events if e.type == "hole_dealt" for c in e.data["cards"] if c not in shown
    } - board

    text = json.dumps(match_analytics("poker", events, False))

    assert not any(f'"{card}"' in text for card in secret)


def test_a_showdown_bluff_is_an_aggressive_hand_that_lost_the_showdown(match):
    _, events = match
    a = match_analytics("poker", events, False)

    for player, totals in a["totals"].items():
        lost = [
            h
            for h in a["hands"]
            if player in h["aggressive"]
            and h["showdown"]
            and any(s["player"] == player for s in h["shown"])
            and not h["winners"].get(player)
        ]
        assert totals["showdown_bluffs"] == len(lost)
        assert totals["showdowns_won"] <= totals["showdowns"]


def test_the_decision_telemetry_of_a_model_move_lands_on_its_move_and_in_the_totals():
    def engine(type, data):
        return Event(source=EventSource.ENGINE, type=type, data=data, visible_to=("p1",))

    def game(type, data):
        return Event(source=EventSource.GAME, type=type, data=data)

    log = [
        engine(
            "match_started", {"game": "poker", "players": ["p1", "p2"], "settings": {}}
        ).model_copy(update={"visible_to": ()}),
        game("hand_started", {"hand": 1, "button": "p1", "players": ["p1", "p2"], "big_blind": 20}),
        game("blind_posted", {"player": "p2", "amount": 20, "kind": "big"}),
        game("street_started", {"street": "preflop", "order": ["p1", "p2"], "cards": []}),
        engine("action_accepted", {"player": "p1"}),
        engine(
            "decision",
            {"player": "p1", "latency_ms": 900, "tokens_in": 300, "tokens_out": 40, "retries": 1},
        ),
        game(
            "bet_action",
            {"player": "p1", "kind": "raise", "street": "preflop", "to": 60, "added": 60},
        ),
        game(
            "bet_action",
            {"player": "p2", "kind": "fold", "street": "preflop", "to": 20, "added": 0},
        ),
        game("pot_awarded", {"amount": 80, "eligible": ["p1"], "shares": {"p1": 80}}),
        game("hand_ended", {"hand": 1, "showdown": False}),
    ]
    a = match_analytics("poker", log, True)

    move = a["moves"][0]
    assert (move["kind"], move["latency_ms"], move["tokens_in"], move["retries"]) == (
        "raise",
        900,
        300,
        1,
    )
    mine = a["totals"]["p1"]
    assert mine["response_ms_mean"] == 900 and mine["tokens"] == 340 and mine["retries_total"] == 1
    assert (mine["hands_won"], mine["raises"], mine["net_chips"]) == (1, 1, 20)
    assert a["totals"]["p2"]["folds"] == 1 and a["totals"]["p2"]["response_ms_mean"] is None
    # the decision events are for spectators only: without spoilers the telemetry is absent
    public = match_analytics("poker", log, False)
    assert public["moves"][0]["latency_ms"] is None and public["totals"]["p1"]["tokens"] is None


def test_without_spoilers_a_refusal_or_a_bot_move_is_unknown_not_zero(match):
    _, events = match
    public = match_analytics("poker", events, False)
    full = match_analytics("poker", events, True)

    assert all(m["fallback"] is None and m["rejected"] is None for m in public["moves"])
    for player, totals in public["totals"].items():
        assert totals["fallbacks"] is None and totals["refused"] is None
        assert full["totals"][player]["fallbacks"] == 0  # bots: no fallback, but known
        assert full["totals"][player]["refused"] == 0
    assert all(m["fallback"] is False for m in full["moves"])


def test_with_spoilers_a_fallback_and_refused_answers_are_counted():
    def engine(type, data):
        return Event(source=EventSource.ENGINE, type=type, data=data, visible_to=("p1",))

    def game(type, data):
        return Event(source=EventSource.GAME, type=type, data=data)

    log = [
        engine(
            "match_started", {"game": "poker", "players": ["p1", "p2"], "settings": {}}
        ).model_copy(update={"visible_to": ()}),
        game("hand_started", {"hand": 1, "button": "p1", "players": ["p1", "p2"], "big_blind": 20}),
        game("blind_posted", {"player": "p2", "amount": 20, "kind": "big"}),
        game("street_started", {"street": "preflop", "order": ["p1", "p2"], "cards": []}),
        engine("action_rejected", {"player": "p1", "tool": "raise", "error": "too small"}),
        engine("action_rejected", {"player": "p1", "tool": "raise", "error": "too small"}),
        engine("action_fallback", {"player": "p1", "reason": "rejected"}),
        game(
            "bet_action", {"player": "p1", "kind": "fold", "street": "preflop", "to": 0, "added": 0}
        ),
        game("pot_awarded", {"amount": 20, "eligible": ["p2"], "shares": {"p2": 20}}),
        game("hand_ended", {"hand": 1, "showdown": False}),
    ]
    a = match_analytics("poker", log, True)

    assert a["moves"][0]["fallback"] is True and a["moves"][0]["rejected"] == 2
    assert (a["totals"]["p1"]["fallbacks"], a["totals"]["p1"]["refused"]) == (1, 2)
    public = match_analytics("poker", log, False)
    assert public["totals"]["p1"]["fallbacks"] is None and public["moves"][0]["fallback"] is None
