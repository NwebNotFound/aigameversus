"""Facts the server reads from a match log, each from one player's point of view."""

import asyncio

import pytest

from arena.agents.random_bot import random_bots
from arena.engine.match import Match
from arena.engine.types import Event, EventSource
from arena.games import load_games
from arena.memory.facts import KINDS, Fact, match_facts, seen_by


def game(type_, data, visible_to=None):
    return Event(source=EventSource.GAME, type=type_, data=data, visible_to=visible_to)


def played(game_id, players, seed):
    plugin = load_games()[game_id]
    seats = [f"p{i}" for i in range(1, players + 1)]
    match = Match(plugin, random_bots(plugin, seats, seed), seed=seed)
    asyncio.run(match.run())
    return match.events, seats


def test_liars_deck_caught_liar_false_accusation_and_honesty():
    log = [
        game(
            "round_started",
            {
                "round": 2,
                "table_card": "queen",
                "starter": "a",
                "hand_size": 5,
                "players": ["a", "b", "c"],
            },
        ),
        game("liar_called", {"caller": "b", "target": "a", "automatic": False}),
        game("cards_revealed", {"player": "a", "cards": ["Q1"], "honest": True, "devil": False}),
        game("liar_called", {"caller": "a", "target": "c", "automatic": False}),
        game("cards_revealed", {"player": "c", "cards": ["K1"], "honest": False, "devil": False}),
    ]

    facts = set(match_facts("liars_deck", log, ["a", "b", "c"]))

    assert facts == {
        Fact(observer="a", about="b", kind="accused_me_falsely", round=2),
        Fact(observer="b", about="a", kind="honest_when_called", round=2),
        Fact(observer="a", about="c", kind="caught_lying", round=2),
        Fact(observer="b", about="c", kind="caught_lying", round=2),
    }


def test_an_automatic_call_blames_nobody():
    log = [
        game(
            "round_started",
            {
                "round": 1,
                "table_card": "ace",
                "starter": "a",
                "hand_size": 5,
                "players": ["a", "b"],
            },
        ),
        game("liar_called", {"caller": "b", "target": "a", "automatic": True}),
        game("cards_revealed", {"player": "a", "cards": ["A1"], "honest": True, "devil": False}),
    ]

    assert match_facts("liars_deck", log, ["a", "b"]) == []


def test_poker_bluff_is_a_raise_that_loses_every_pot_of_the_showdown():
    def hand(no, side_pot_for_b):
        return [
            game("hand_started", {"hand": no}),
            game("street_started", {"street": "preflop", "order": ["a", "b", "c"], "cards": []}),
            game("blind_posted", {"player": "a", "amount": 10, "kind": "small"}),
            game(
                "bet_action",
                {"player": "b", "kind": "raise", "street": "preflop", "to": 60, "added": 60},
            ),
            game(
                "bet_action",
                {"player": "c", "kind": "call", "street": "preflop", "to": 60, "added": 60},
            ),
            game(
                "bet_action",
                {"player": "a", "kind": "fold", "street": "preflop", "to": 10, "added": 0},
            ),
            game(
                "showdown",
                {
                    "hands": [
                        {"player": "b", "cards": [], "hand": "high_card"},
                        {"player": "c", "cards": [], "hand": "pair"},
                    ]
                },
            ),
            game("pot_awarded", {"amount": 130, "eligible": ["b", "c"], "shares": {"c": 130}}),
            *(
                [game("pot_awarded", {"amount": 20, "eligible": ["b"], "shares": {"b": 20}})]
                if side_pot_for_b
                else []
            ),
            game("hand_ended", {"hand": no, "showdown": True}),
        ]

    facts = match_facts("poker", [*hand(4, False), *hand(5, True)], ["a", "b", "c"])

    # Everyone in the hand saw b raise and lose; with a side pot b did not lose it.
    assert sorted(facts, key=lambda f: f.observer) == [
        Fact(observer="a", about="b", kind="bluff_called", round=4),
        Fact(observer="c", about="b", kind="bluff_called", round=4),
    ]


def test_werewolf_votes_lovers_pack_and_exposed_wolves():
    log = [
        game("role_assigned", {"player": "s", "role": "seer"}, ["s"]),
        game("pack_revealed", {"wolves": ["w", "x"]}, ["w", "x"]),
        game("love_revealed", {"lovers": ["s", "v"]}, ["s", "v"]),
        game("night_started", {"night": 1}),
        game("seer_inspected", {"player": "s", "target": "w", "role": "werewolf"}, ["s"]),
        game("day_started", {"day": 1, "order": ["s", "v", "w", "x"]}),
        game("vote_cast", {"player": "v", "target": "s"}),
        game("vote_cast", {"player": "w", "target": "v"}),
        game("player_died", {"player": "w", "cause": "vote", "role": "werewolf"}),
    ]

    facts = set(match_facts("werewolf", log, ["s", "v", "w", "x"]))

    assert facts == {
        Fact(observer="w", about="x", kind="packmate"),
        Fact(observer="x", about="w", kind="packmate"),
        # The seer learns it at night, the others when the wolf dies; nobody twice.
        Fact(observer="s", about="w", kind="revealed_wolf", round=None),
        Fact(observer="v", about="w", kind="revealed_wolf", round=1),
        Fact(observer="x", about="w", kind="revealed_wolf", round=1),
        Fact(observer="s", about="v", kind="lover_voted_against_me", round=1),
        Fact(observer="v", about="w", kind="voted_against_me", round=1),
    }


def test_a_game_without_facts_has_none():
    events, seats = played("toy", 2, 1)

    assert match_facts("toy", events, seats) == []


@pytest.mark.parametrize(
    ("game_id", "players", "seed"),
    [("liars_deck", 4, 3), ("poker", 4, 3), ("werewolf", 10, 3), ("werewolf", 12, 8)],
)
def test_a_players_facts_come_only_from_what_that_player_saw(game_id, players, seed):
    events, seats = played(game_id, players, seed)
    facts = match_facts(game_id, events, seats)

    assert facts, "a bot match of this game should produce facts"
    assert {f.kind for f in facts} <= KINDS[game_id]
    for player in seats:
        own = [f for f in facts if f.observer == player]
        # The same facts from nothing but the player's own view of the log.
        alone = [
            f for f in match_facts(game_id, seen_by(events, player), seats) if f.observer == player
        ]
        assert own == alone
        assert all(f.about != player and f.about in seats for f in own)


def test_facts_are_the_same_for_the_same_log():
    events, seats = played("werewolf", 9, 5)

    assert match_facts("werewolf", events, seats) == match_facts("werewolf", events, seats)


@pytest.mark.parametrize("seed", [1, 2, 3, 4, 5, 6])
def test_only_the_seer_learns_of_a_wolf_that_is_still_alive(seed):
    events, seats = played("werewolf", 10, seed)
    roles = {e.data["player"]: e.data["role"] for e in events if e.type == "role_assigned"}
    dead = {e.data["player"] for e in events if e.type == "player_died"}

    for fact in match_facts("werewolf", events, seats):
        if fact.kind == "revealed_wolf" and roles[fact.observer] != "seer":
            assert fact.about in dead, fact
