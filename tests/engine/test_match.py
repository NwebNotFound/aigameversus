import asyncio

import pytest

from arena.agents.random_bot import random_bots
from arena.engine.match import Match, PluginError
from arena.engine.types import Action, EventSource

from .counter_game import (
    Scripted,
    SequentialCounter,
    SimultaneousCounter,
    TickCounter,
    add,
)

PLAYERS = ["ada", "bo"]
ALL_MODES = [SequentialCounter, SimultaneousCounter, TickCounter]


def play(plugin, agents, *, seed=1, settings=None):
    match = Match(plugin, agents, seed=seed, settings=settings)
    placements = asyncio.run(match.run())
    return match, placements


def bot_match(plugin_class, *, seed=1, rounds=4):
    plugin = plugin_class()
    return play(plugin, random_bots(plugin, PLAYERS, seed), seed=seed, settings={"rounds": rounds})


def types(match, source=None):
    return [e.type for e in match.events if source is None or e.source is source]


@pytest.mark.parametrize("plugin_class", ALL_MODES)
def test_bot_match_runs_to_the_end_in_every_turn_mode(plugin_class):
    match, placements = bot_match(plugin_class)

    assert sorted(p.player for p in placements) == PLAYERS
    assert match.state.clock == 4
    assert types(match)[0] == "match_started"
    assert types(match)[-1] == "match_finished"
    assert match.events[-1].data["placements"] == [p.model_dump() for p in placements]


@pytest.mark.parametrize("plugin_class", ALL_MODES)
def test_same_seed_gives_the_same_match(plugin_class):
    first, first_placements = bot_match(plugin_class, seed=7)
    second, second_placements = bot_match(plugin_class, seed=7)

    assert first.events == second.events
    assert first.state == second.state
    assert first_placements == second_placements


def test_another_seed_gives_another_match():
    first, _ = bot_match(SequentialCounter, seed=7, rounds=8)
    second, _ = bot_match(SequentialCounter, seed=8, rounds=8)

    assert first.events != second.events


def test_tick_mode_advances_on_ticks_without_decisions():
    match, _ = bot_match(TickCounter, rounds=4)

    # Players act on ticks 0 and 2 only; ticks 1 and 3 pass by `step` alone.
    assert types(match, EventSource.GAME) == [
        "added",
        "added",
        "round_closed",
        "round_closed",
        "added",
        "added",
        "round_closed",
        "round_closed",
    ]


def test_simultaneous_players_decide_on_the_same_state():
    ada, bo = Scripted(add(1), add(2)), Scripted(add(3), add(1))

    play(SimultaneousCounter(), {"ada": ada, "bo": bo})

    # Neither player saw the other's amount of the same round.
    assert ada.requests[0].observation["amounts"] == {"ada": [], "bo": []}
    assert bo.requests[0].observation["amounts"] == {"ada": [], "bo": []}
    assert ada.requests[1].observation["amounts"] == {"ada": [1], "bo": [3]}


def test_sequential_players_see_earlier_moves_of_the_round():
    ada, bo = Scripted(add(1), add(2)), Scripted(add(3), add(1))

    play(SequentialCounter(), {"ada": ada, "bo": bo})

    assert bo.requests[0].observation["amounts"] == {"ada": [1], "bo": []}


def test_unavailable_tool_is_rejected_and_can_be_corrected():
    ada = Scripted(Action(tool="steal", arguments={}), add(1), add(2))

    match, _ = play(SequentialCounter(), {"ada": ada, "bo": Scripted(add(1), add(2))})

    assert ada.requests[0].error is None
    assert ada.requests[1].error == "Tool 'steal' is not available now. Available tools: add."
    assert match.state.amounts["ada"] == [1, 2]
    assert types(match)[1:4] == ["action_rejected", "action_accepted", "added"]


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        ({"amount": 9}, "9 is greater than the maximum of 3"),
        ({"amount": "two"}, "'two' is not of type 'integer'"),
        ({}, "'amount' is a required property"),
        ({"amount": 1, "extra": True}, "Additional properties are not allowed"),
    ],
)
def test_arguments_that_break_the_schema_are_rejected(arguments, message):
    ada = Scripted(Action(tool="add", arguments=arguments), add(1), add(2))

    match, _ = play(SequentialCounter(), {"ada": ada, "bo": Scripted(add(1), add(2))})

    assert ada.requests[1].error.startswith("Invalid arguments for 'add': ")
    assert message in ada.requests[1].error
    assert match.state.amounts["ada"] == [1, 2]


def test_rule_violation_is_explained_to_the_player():
    ada = Scripted(add(1), add(1), add(3))

    match, _ = play(SequentialCounter(), {"ada": ada, "bo": Scripted(add(1), add(2))})

    assert ada.requests[2].error == "You may not add the same amount twice in a row."
    assert match.state.amounts["ada"] == [1, 3]


def test_random_fallback_plays_after_two_failed_corrections():
    ada = Scripted(add(0), add(0), add(0), add(2))

    match, _ = play(SequentialCounter(), {"ada": ada, "bo": Scripted(add(3), add(1))})

    # First attempt plus two corrections, then the engine stops asking for this turn.
    assert [request.error is None for request in ada.requests] == [True, False, False, True]
    assert types(match)[1:6] == [
        "action_rejected",
        "action_rejected",
        "action_rejected",
        "action_fallback",
        "added",
    ]
    fallback = match.events[4].data
    assert fallback["player"] == "ada"
    assert match.state.amounts["ada"][0] == fallback["arguments"]["amount"]


def test_fallback_is_deterministic():
    def run():
        ada = Scripted(*[add(0)] * 6)
        return play(SequentialCounter(), {"ada": ada, "bo": Scripted(add(1), add(2))}, seed=3)[0]

    assert run().events == run().events


def test_players_cannot_see_the_seed_or_each_others_attempts():
    ada = Scripted(add(0), add(1), add(2))
    match, _ = play(SequentialCounter(), {"ada": ada, "bo": Scripted(add(1), add(2))})

    visible_to_bo = [event for event in match.events if event.is_visible_to("bo")]

    assert "match_started" not in [event.type for event in visible_to_bo]
    assert all("seed" not in event.data for event in visible_to_bo)
    assert {
        event.data["player"] for event in visible_to_bo if event.type.startswith("action_")
    } == {"bo"}


@pytest.mark.parametrize("players", [["solo"], ["a", "b", "c", "d"]])
def test_wrong_number_of_players_is_refused(players):
    plugin = SequentialCounter()

    with pytest.raises(ValueError, match="counter needs 2 to 3 players"):
        Match(plugin, random_bots(plugin, players, 1), seed=1)


class TwoAtOnce(SequentialCounter):
    def active_players(self, state):
        return list(state.waiting)


class NeverCloses(SequentialCounter):
    def step(self, state, ctx):
        pass


class ReusesStream(SequentialCounter):
    def step(self, state, ctx):
        ctx.rng("bonus")
        super().step(state, ctx)


class IllegalBot(SequentialCounter):
    def random_action(self, observation, tools, rng):
        return add(0)


@pytest.mark.parametrize(
    ("plugin_class", "message"),
    [
        (TwoAtOnce, "counter is sequential but has 2 active players"),
        (NeverCloses, "counter made no progress"),
        (ReusesStream, r"counter asked for random stream \('bonus',\) twice"),
        (IllegalBot, "random_action of counter is not legal"),
    ],
)
def test_plugin_that_breaks_the_contract_stops_the_match(plugin_class, message):
    plugin = plugin_class()
    agents = {"ada": Scripted(*[add(0)] * 3), "bo": Scripted(add(1), add(2))}
    if plugin_class is not IllegalBot:
        agents = random_bots(plugin, PLAYERS, 1)

    with pytest.raises(PluginError, match=message):
        play(plugin, agents)
