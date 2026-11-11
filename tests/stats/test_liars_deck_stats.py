import asyncio

import pytest

from arena.agents.random_bot import random_bots
from arena.engine.match import Match
from arena.engine.types import Event, EventSource
from arena.stats.liars_deck import LiarsDeckMatchStats, aggregate, match_stats
from games.liars_deck.plugin import LiarsDeck


def engine(type, data):
    return Event(source=EventSource.ENGINE, type=type, data=data, visible_to=())


def game(type, data):
    return Event(source=EventSource.GAME, type=type, data=data)


def log(*events):
    start = engine(
        "match_started",
        {"game": "liars_deck", "version": "1", "players": ["p1", "p2"], "settings": {}, "seed": 1},
    )
    loaded = [game("revolver_loaded", {"player": p, "live": [0]}) for p in ("p1", "p2")]
    return [start, *loaded, *events]


def round_started(number, table_card="king"):
    return game(
        "round_started",
        {"round": number, "table_card": table_card, "starter": "p1", "hand_size": 5,
         "players": ["p1", "p2"]},
    )  # fmt: skip


def play(player, cards):
    return [
        game("cards_played", {"player": player, "count": len(cards)}),
        game("cards_hidden", {"player": player, "cards": cards}),
    ]


def call(caller, target, cards, *, automatic=False):
    honest = all(c[0] in ("K", "J") or c == "DV" for c in cards)  # table card is king
    return [
        game("liar_called", {"caller": caller, "target": target, "automatic": automatic}),
        game(
            "cards_revealed",
            {"player": target, "cards": cards, "honest": honest, "devil": False},
        ),
    ]


def pull(player, number, live):
    return game("trigger_pulled", {"player": player, "pull": number, "live": live})


def test_hand_built_log_counts_lies_calls_and_the_boldest_bluff():
    events = log(
        round_started(1),
        *play("p1", ["K1", "J1"]),  # honest: a king and a joker
        *play("p2", ["Q1"]),  # a lie
        *call("p1", "p2", ["Q1"]),  # p1 calls correctly
        pull("p2", 1, False),
        round_started(2),
        *play("p2", ["Q2", "A1"]),  # a lie, the revolver has had one pull: risk 1/5
        *play("p1", ["K2"]),  # honest
        *call("p2", "p1", ["K2"]),  # p2 calls wrongly
        pull("p2", 2, True),
    )

    stats = match_stats(events)

    assert stats["p1"] == LiarsDeckMatchStats(
        player="p1", plays=2, lies=0, calls=1, calls_correct=1, rounds_played=2
    )
    assert stats["p2"] == LiarsDeckMatchStats(
        player="p2", plays=2, lies=2, times_caught=1, calls=1, calls_correct=0,
        rounds_played=2, eliminated=True, boldest_bluff_risk=1 / 5,
    )  # fmt: skip


def test_an_automatic_call_is_not_a_chosen_call_but_still_catches_a_liar():
    events = log(
        round_started(1),
        *play("p1", ["Q1"]),
        *call("p2", "p1", ["Q1"], automatic=True),
    )

    stats = match_stats(events)

    assert (stats["p2"].calls, stats["p2"].calls_correct) == (0, 0)
    assert stats["p1"].times_caught == 1


def test_a_log_of_another_game_is_refused():
    with pytest.raises(ValueError, match="Liar's Deck"):
        match_stats([engine("match_started", {"game": "poker", "settings": {}, "players": []})])


def test_aggregate_adds_matches_up_and_has_no_rates_without_data():
    empty = aggregate([])
    assert (empty.matches, empty.lie_rate, empty.call_success_rate) == (0, None, None)
    assert (empty.rounds_survived_per_match, empty.boldest_bluff_risk) == (None, None)

    first = LiarsDeckMatchStats(
        player="p1", plays=4, lies=2, times_caught=1, calls=2, calls_correct=1,
        rounds_played=3, eliminated=True, boldest_bluff_risk=0.2,
    )  # fmt: skip
    second = LiarsDeckMatchStats(
        player="p1", plays=6, lies=1, calls=0, rounds_played=5, boldest_bluff_risk=0.5
    )

    totals = aggregate([first, second])

    assert (totals.matches, totals.plays, totals.lies) == (2, 10, 3)
    assert totals.lie_rate == pytest.approx(0.3)
    assert totals.caught_share == pytest.approx(1 / 3)
    assert totals.call_success_rate == pytest.approx(0.5)
    assert totals.eliminations == 1
    assert totals.rounds_survived_per_match == pytest.approx((8 - 1) / 2)  # rounds minus the fall
    assert totals.boldest_bluff_risk == 0.5


def bot_log(players, seed, settings=None):
    plugin = LiarsDeck()
    names = [f"p{i}" for i in range(1, players + 1)]
    match = Match(plugin, random_bots(plugin, names, seed), seed=seed, settings=settings)
    asyncio.run(match.run())
    return match.events


@pytest.mark.parametrize("variant", ["base", "devil_card"])
@pytest.mark.parametrize("players", [2, 3, 4])
def test_real_bot_matches_are_consistent_with_their_own_events(players, variant):
    for seed in range(1, 6):
        events = bot_log(players, seed, {"variant": variant})
        stats = match_stats(events)

        reveals = [e for e in events if e.type == "cards_revealed"]
        calls = [e for e in events if e.type == "liar_called" and not e.data["automatic"]]
        assert sum(s.times_caught for s in stats.values()) == sum(
            not e.data["honest"] for e in reveals
        )
        assert sum(s.calls for s in stats.values()) == len(calls)
        for s in stats.values():
            assert s.times_caught <= s.lies <= s.plays
            assert s.calls_correct <= s.calls
            assert s.rounds_played >= 1
            assert s.boldest_bluff_risk is None or 0 < s.boldest_bluff_risk <= 1
        # The stats count falls the way the log does.
        fallen = {p for e in events if e.type == "players_eliminated" for p in e.data["players"]}
        assert {p for p, s in stats.items() if s.eliminated} == fallen


def test_the_same_log_gives_the_same_statistics():
    events = bot_log(3, 9)

    assert match_stats(events) == match_stats(events)


def test_the_registry_finds_liars_deck_by_game_id():
    from arena.stats import STATS

    stats = STATS["liars_deck"]
    per_player = stats.match_stats(bot_log(2, 3))

    assert set(per_player) == {"p1", "p2"}
    assert stats.aggregate([per_player["p1"]]).matches == 1
