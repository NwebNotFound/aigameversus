import asyncio

import pytest

from arena.agents.random_bot import random_bots
from arena.engine.match import Match
from arena.engine.types import Event, EventSource
from arena.stats import STATS
from arena.stats.poker import PokerMatchStats, aggregate, match_stats
from games.poker.plugin import Poker


def game(type, data):
    return Event(source=EventSource.GAME, type=type, data=data)


def start(players):
    data = {"game": "poker", "version": "1", "players": players, "settings": {}, "seed": 1}
    return Event(source=EventSource.ENGINE, type="match_started", data=data, visible_to=())


def hand_started(players, number=1):
    return game(
        "hand_started",
        {
            "hand": number,
            "button": players[0],
            "players": players,
            "big_blind": 20,
            "small_blind": 10,
            "small_blind_player": players[1],
            "big_blind_player": players[-1],
        },
    )


def hole(player, *cards):
    return game("hole_dealt", {"player": player, "cards": list(cards)})


def blind(player, amount):
    return game("blind_posted", {"player": player, "amount": amount, "kind": "x"})


def street(name, *cards):
    return game("street_started", {"street": name, "order": [], "cards": list(cards)})


def act(player, kind, street_name, to, added):
    data = {"player": player, "kind": kind, "street": street_name, "to": to, "added": added}
    return game("bet_action", data)


def award(amount, **shares):
    return game("pot_awarded", {"amount": amount, "eligible": list(shares), "shares": shares})


def ended(number=1, showdown=False):
    return game("hand_ended", {"hand": number, "showdown": showdown})


def test_a_raise_that_wins_without_showdown_with_a_weak_hand_is_a_bluff():
    events = [
        start(["p1", "p2"]),
        hand_started(["p1", "p2"]),
        hole("p2", "7c", "2d"),
        hole("p1", "Ah", "Ad"),
        blind("p2", 10),
        blind("p1", 20),
        street("preflop"),
        act("p2", "raise", "preflop", 60, 50),
        act("p1", "fold", "preflop", 20, 0),
        award(80, p2=80),
        ended(),
    ]

    stats = match_stats(events)

    assert stats["p2"] == PokerMatchStats(
        player="p2",
        hands=1,
        vpip_hands=1,
        aggressive_actions=1,
        aggressive_hands=1,
        bluff_hands=1,
        net_chips=20,
    )
    assert stats["p1"] == PokerMatchStats(player="p1", hands=1, net_chips=-20)


def showdown_where_p1_folds_the_best_hand(p3_flop_kind="call", p3_flop_to=40):
    players = ["p1", "p2", "p3"]
    return [
        start(players),
        hand_started(players),
        hole("p1", "Ah", "Ad"),
        hole("p2", "Kc", "Kd"),
        hole("p3", "Qc", "Qd"),
        blind("p2", 10),
        blind("p3", 20),
        street("preflop"),
        act("p1", "call", "preflop", 20, 20),
        act("p2", "call", "preflop", 20, 10),
        act("p3", "check", "preflop", 0, 0),
        street("flop", "As", "7c", "2d"),
        act("p2", "raise", "flop", 40, 40),
        act("p3", p3_flop_kind, "flop", p3_flop_to, 40),
        act("p1", "fold", "flop", 0, 0),
        street("turn", "9h"),
        street("river", "3s"),
        game(
            "showdown",
            {
                "hands": [
                    {"player": "p2", "cards": ["Kc", "Kd"], "hand": "one_pair"},
                    {"player": "p3", "cards": ["Qc", "Qd"], "hand": "one_pair"},
                ]
            },
        ),
        award(140, p2=140),
        ended(showdown=True),
    ]


def test_folding_the_best_hand_before_a_showdown_is_the_worst_decision():
    stats = match_stats(showdown_where_p1_folds_the_best_hand())

    p1, p2, p3 = stats["p1"], stats["p2"], stats["p3"]
    assert (p1.worst_decisions, p1.vpip_hands, p1.calls, p1.net_chips) == (1, 1, 1, -20)
    # p2 raised on the flop and won the showdown: aggressive, not a bluff.
    assert (p2.aggressive_actions, p2.calls, p2.bluff_hands, p2.net_chips) == (1, 1, 0, 80)
    # p3 only checked before the flop (no VPIP) and called the flop bet.
    assert (p3.vpip_hands, p3.calls, p3.net_chips, p3.worst_decisions) == (0, 1, -60, 0)


def test_a_raise_that_loses_at_the_showdown_is_a_bluff_hand():
    events = showdown_where_p1_folds_the_best_hand(p3_flop_kind="raise", p3_flop_to=80)

    assert match_stats(events)["p3"].bluff_hands == 1


def test_a_log_of_another_game_is_refused():
    event = Event(
        source=EventSource.ENGINE, type="match_started", data={"game": "toy", "players": []}
    )
    with pytest.raises(ValueError, match="Poker"):
        match_stats([event])


def test_aggregate_adds_matches_up_and_has_no_rates_without_data():
    empty = aggregate([])
    assert (empty.vpip, empty.aggression_factor, empty.bluff_rate) == (None, None, None)
    assert empty.chips_per_100_hands is None

    one = PokerMatchStats(
        player="p1",
        hands=10,
        vpip_hands=4,
        aggressive_actions=6,
        calls=3,
        aggressive_hands=4,
        bluff_hands=1,
        net_chips=-50,
        worst_decisions=1,
    )
    two = PokerMatchStats(
        player="p1",
        hands=10,
        vpip_hands=6,
        aggressive_actions=2,
        calls=1,
        aggressive_hands=2,
        bluff_hands=1,
        net_chips=250,
    )

    totals = aggregate([one, two])

    assert (totals.matches, totals.hands, totals.worst_decisions) == (2, 20, 1)
    assert totals.vpip == pytest.approx(0.5)
    assert totals.aggression_factor == pytest.approx(2.0)
    assert totals.bluff_rate == pytest.approx(2 / 6)
    assert totals.chips_per_100_hands == pytest.approx(1000.0)


def bot_log(players, seed):
    plugin = Poker()
    names = [f"p{i}" for i in range(1, players + 1)]
    match = Match(plugin, random_bots(plugin, names, seed), seed=seed)
    asyncio.run(match.run())
    return match.events


@pytest.mark.parametrize("players", [2, 3, 6])
def test_real_bot_matches_are_consistent_with_their_own_events(players):
    for seed in range(1, 4):
        events = bot_log(players, seed)
        stats = match_stats(events)

        hands_started = [e for e in events if e.type == "hand_started"]
        assert sum(s.hands for s in stats.values()) == sum(
            len(e.data["players"]) for e in hands_started
        )
        # Every chip a player wins, another one put in.
        assert sum(s.net_chips for s in stats.values()) == 0
        for s in stats.values():
            assert s.vpip_hands <= s.hands
            assert s.bluff_hands <= s.aggressive_hands <= s.hands
            assert s.worst_decisions <= s.hands


def test_the_registry_finds_poker_by_game_id():
    per_player = STATS["poker"].match_stats(bot_log(2, 5))

    assert set(per_player) == {"p1", "p2"}
    assert STATS["poker"].aggregate([per_player["p1"]]).matches == 1
