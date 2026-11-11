import asyncio

import pytest

from arena.agents.random_bot import random_bots
from arena.engine.match import Match
from arena.engine.types import Event, EventSource
from arena.stats import STATS
from arena.stats.werewolf import WerewolfMatchStats, aggregate, match_stats
from games.werewolf.plugin import Werewolf

PLAYERS = ["p1", "p2", "p3", "p4"]


def game(type, data):
    return Event(source=EventSource.GAME, type=type, data=data)


def start(players=PLAYERS):
    data = {"game": "werewolf", "version": "1", "players": players, "settings": {}, "seed": 1}
    return Event(source=EventSource.ENGINE, type="match_started", data=data, visible_to=())


def roles(**by_player):
    return [game("role_assigned", {"player": p, "role": r}) for p, r in by_player.items()]


def vote(player, target):
    return game("vote_cast", {"player": player, "target": target})


def died(player, cause, role="villager"):
    return game("player_died", {"player": player, "cause": cause, "role": role})


def hand_built_log():
    return [
        start(),
        *roles(p1="seer", p2="werewolf", p3="villager", p4="villager"),
        game("pack_revealed", {"wolves": ["p2"]}),
        game("night_started", {"night": 1}),
        vote("p1", "p2"),  # the seer votes the wolf
        vote("p2", "p3"),  # a wolf's vote is left out
        vote("p3", "p4"),  # a villager votes a villager
        vote("p4", None),  # an abstention
        died("p3", "executed"),
        game("night_started", {"night": 2}),
        died("p1", "wolves", "seer"),
        game("game_over", {"winner": "wolves", "winners": ["p2"]}),
    ]


def test_hand_built_log_counts_votes_rounds_and_the_seer():
    stats = match_stats(hand_built_log())

    assert stats["p1"] == WerewolfMatchStats(
        player="p1",
        role="seer",
        died=True,
        death_cause="wolves",
        rounds_alive=2,
        votes_for_wolves=1,
    )
    assert stats["p2"].won and not stats["p2"].died and stats["p2"].rounds_alive == 2
    assert (stats["p2"].votes_for_wolves, stats["p2"].votes_for_villagers) == (0, 0)
    assert (stats["p3"].votes_for_villagers, stats["p3"].rounds_alive) == (1, 1)
    assert (stats["p4"].abstentions, stats["p4"].rounds_alive, stats["p4"].won) == (1, 2, False)


def test_a_player_who_joins_the_pack_votes_as_a_wolf_from_then_on():
    events = [
        start(),
        *roles(p1="wild_child", p2="werewolf", p3="villager", p4="villager"),
        game("pack_revealed", {"wolves": ["p2"]}),
        game("night_started", {"night": 1}),
        vote("p1", "p2"),  # still on the village side: a hit
        game("joined_pack", {"player": "p1"}),
        vote("p1", "p3"),  # now a wolf: left out
    ]

    me = match_stats(events)["p1"]

    assert (me.votes_for_wolves, me.votes_for_villagers) == (1, 0)


def test_an_infected_player_is_a_wolf_for_the_votes_after_the_infection():
    events = [
        start(),
        *roles(p1="seer", p2="prime_wolf", p3="villager", p4="villager"),
        game("pack_revealed", {"wolves": ["p2"]}),
        game("night_started", {"night": 1}),
        vote("p3", "p4"),  # before the infection p3 is a villager: a miss
        game("infected", {"player": "p3"}),
        vote("p3", "p4"),  # now a wolf: left out
        vote("p1", "p3"),  # the seer hits the infected player: a wolf
    ]

    stats = match_stats(events)

    assert (stats["p3"].votes_for_wolves, stats["p3"].votes_for_villagers) == (0, 1)
    assert (stats["p1"].votes_for_wolves, stats["p1"].votes_for_villagers) == (1, 0)


def test_a_log_of_another_game_is_refused():
    event = Event(
        source=EventSource.ENGINE, type="match_started", data={"game": "toy", "players": []}
    )
    with pytest.raises(ValueError, match="Werewolf"):
        match_stats([event])


def test_aggregate_adds_matches_up_and_the_seer_has_her_own_numbers():
    empty = aggregate([])
    assert (empty.vote_accuracy, empty.win_rate, empty.rounds_alive_per_match) == (None, None, None)
    assert empty.seer_rounds_alive_per_match is None

    seer_dead = WerewolfMatchStats(
        player="p1", role="seer", died=True, rounds_alive=1, votes_for_wolves=1
    )
    seer_alive = WerewolfMatchStats(
        player="p1",
        role="seer",
        won=True,
        rounds_alive=5,
        votes_for_wolves=2,
        votes_for_villagers=1,
    )
    villager = WerewolfMatchStats(player="p1", role="villager", rounds_alive=3, abstentions=2)

    totals = aggregate([seer_dead, seer_alive, villager])

    assert (totals.matches, totals.wins, totals.deaths) == (3, 1, 1)
    assert totals.vote_accuracy == pytest.approx(3 / 4)
    assert totals.win_rate == pytest.approx(1 / 3)
    assert totals.rounds_alive_per_match == pytest.approx(3.0)
    assert (totals.seer_matches, totals.seer_deaths) == (2, 1)
    assert totals.seer_rounds_alive_per_match == pytest.approx(3.0)
    assert totals.abstentions == 2


def bot_log(players, seed, **settings):
    plugin = Werewolf()
    names = [f"p{i}" for i in range(1, players + 1)]
    match = Match(plugin, random_bots(plugin, names, seed), seed=seed, settings=settings)
    asyncio.run(match.run())
    return match.events


@pytest.mark.parametrize(
    ("players", "settings"),
    [(6, {}), (8, {}), (12, {}), (16, {"template": "chaos"})],
)
def test_real_bot_matches_are_consistent_with_their_own_events(players, settings):
    for seed in range(1, 4):
        events = bot_log(players, seed, **settings)
        stats = match_stats(events)

        died_in_log = {e.data["player"]: e.data["cause"] for e in events if e.type == "player_died"}
        winners = next(e for e in events if e.type == "game_over").data["winners"]
        assert {p for p, s in stats.items() if s.died} == set(died_in_log)
        assert {p: s.death_cause for p, s in stats.items() if s.died} == died_in_log
        assert {p for p, s in stats.items() if s.won} == set(winners)
        casts = [e for e in events if e.type == "vote_cast"]
        assert sum(
            s.votes_for_wolves + s.votes_for_villagers + s.abstentions for s in stats.values()
        ) <= len(casts)
        assert all(s.role is not None and s.rounds_alive >= 1 for s in stats.values())


def test_the_registry_finds_werewolf_by_game_id():
    per_player = STATS["werewolf"].match_stats(bot_log(6, 2))

    assert len(per_player) == 6
    assert STATS["werewolf"].aggregate([per_player["p1"]]).matches == 1
