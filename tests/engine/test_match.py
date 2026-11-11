import asyncio
import json

import pytest

from arena.agents.random_bot import random_bots
from arena.engine.match import Match, PluginError
from arena.engine.types import MESSAGE, Action, AgentError, EventSource, Reply

from .counter_game import (
    HANGS,
    Scripted,
    SequentialCounter,
    SimultaneousCounter,
    TickCounter,
    add,
)

PLAYERS = ["ada", "bo"]
ALL_MODES = [SequentialCounter, SimultaneousCounter, TickCounter]


def play(plugin, agents, *, seed=1, settings=None, turn_timeout=60):
    match = Match(plugin, agents, seed=seed, settings=settings, turn_timeout=turn_timeout)
    placements = asyncio.run(match.run())
    return match, placements


async def run_to_turn_limit(match):
    """Run a match that must stop at its turn limit. One that plays on fails instead of hanging."""
    try:
        async with asyncio.timeout(10):
            return await match.run()
    except TimeoutError:
        pytest.fail("match did not stop at its turn limit")


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
    assert (fallback["player"], fallback["reason"]) == ("ada", "rejected")
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


def test_thought_is_logged_before_the_action_for_spectators_only():
    ada = Scripted(Reply(action=add(1), thought="bo looks weak"), add(2))

    match, _ = play(SequentialCounter(), {"ada": ada, "bo": Scripted(add(1), add(2))})

    assert types(match)[1:4] == ["thought", "action_accepted", "added"]
    thought = match.events[1]
    assert thought.source is EventSource.ENGINE
    assert thought.data == {"player": "ada", "text": "bo looks weak"}
    assert thought.visible_to == ()


def test_request_holds_exactly_the_events_the_player_may_see():
    ada = Scripted(Reply(action=add(0), thought="oops"), add(1), add(2))
    bo = Scripted(add(3), add(1))

    match, _ = play(SequentialCounter(), {"ada": ada, "bo": bo})

    def seen(request):
        return [event.type for event in request.events]

    # A correction shows the own rejected attempt, but never the own thought.
    assert [seen(request) for request in ada.requests] == [
        [],
        ["action_rejected"],
        ["action_rejected", "action_accepted", "added", "added", "round_closed"],
    ]
    assert ada.requests[1].events == (match.events[2],)
    # Bo sees the public moves and his own: not the seed, ada's attempts or her thought.
    assert [seen(request) for request in bo.requests] == [
        ["added"],
        ["added", "action_accepted", "added", "round_closed", "added"],
    ]


def test_reply_without_an_action_is_rejected_with_its_problem():
    ada = Scripted(Reply(problem="No tool call.", thought="hm"), add(1), add(2))

    match, _ = play(SequentialCounter(), {"ada": ada, "bo": Scripted(add(1), add(2))})

    assert ada.requests[1].error == "No tool call."
    assert types(match)[1:4] == ["thought", "action_rejected", "action_accepted"]
    assert match.events[2].data == {
        "player": "ada",
        "tool": None,
        "arguments": None,
        "error": "No tool call.",
    }


@pytest.mark.parametrize("fields", [{}, {"action": add(1), "problem": "No tool call."}])
def test_reply_needs_either_an_action_or_a_problem(fields):
    with pytest.raises(ValueError, match="either an action or a problem"):
        Reply(**fields)


def test_player_who_runs_out_of_time_gets_a_random_action_for_that_turn():
    ada = Scripted(add(0), HANGS, add(2))
    agents = {"ada": ada, "bo": Scripted(add(1), add(2))}

    match, _ = play(SequentialCounter(), agents, turn_timeout=0.2)

    # The time covers the whole turn: the attempt before the timeout stays in the log.
    assert types(match)[1:4] == ["action_rejected", "action_fallback", "added"]
    fallback = match.events[2]
    assert (fallback.data["player"], fallback.data["reason"]) == ("ada", "timeout")
    assert fallback.visible_to == ("ada",)
    # On her next turn ada is asked again and plays herself.
    assert match.state.amounts["ada"] == [fallback.data["arguments"]["amount"], 2]


def test_slow_player_does_not_change_the_order_of_the_log():
    ada, bo = Scripted(HANGS, add(1)), Scripted(add(3), add(2))

    match, _ = play(SimultaneousCounter(), {"ada": ada, "bo": bo}, turn_timeout=0.2)

    # Bo answered long before ada's time ran out, yet the log keeps the seat order.
    assert types(match)[1:6] == [
        "action_fallback",
        "action_accepted",
        "added",
        "added",
        "round_closed",
    ]
    assert match.state.amounts["bo"] == [3, 2]


def test_agent_that_gives_up_loses_its_seat_to_random_actions():
    ada = Scripted(AgentError("model call failed after 4 tries (Timeout)"))

    match, _ = play(SequentialCounter(), {"ada": ada, "bo": Scripted(add(1), add(2))})

    assert types(match)[1:4] == ["agent_failed", "action_fallback", "added"]
    failed = match.events[1]
    assert failed.data == {"player": "ada", "error": "model call failed after 4 tries (Timeout)"}
    assert failed.visible_to == ()
    fallbacks = [event.data for event in match.events if event.type == "action_fallback"]
    assert [(data["player"], data["reason"]) for data in fallbacks] == [("ada", "agent_failed")] * 2
    # It is asked once and never again, and the log marks the failure once.
    assert len(ada.requests) == 1
    assert types(match).count("agent_failed") == 1
    assert match.state.amounts["ada"] == [data["arguments"]["amount"] for data in fallbacks]


def test_what_an_agent_writes_is_made_storable():
    odd = Reply(
        action=Action(
            tool="add\x00", arguments={"amount": float("nan"), "no\ud800te": ("x\x00", 1e999)}
        ),
        thought="a\x00b\udfff",
    )
    agents = {"ada": Scripted(odd, add(1), add(2)), "bo": Scripted(add(1), add(2))}

    match, _ = play(SequentialCounter(), agents)

    assert match.events[1].data == {"player": "ada", "text": "ab"}
    rejected = match.events[2].data
    assert rejected["tool"] == "add"
    assert rejected["arguments"] == {"amount": None, "note": ["x", None]}
    for event in match.events:
        stored = json.dumps(event.data, allow_nan=False, ensure_ascii=False)  # raises on NaN
        stored.encode()  # raises on half a surrogate pair
        assert "\\u0000" not in stored


@pytest.mark.parametrize(
    "data",
    [
        {"player": "ada"},
        {"player": "ada", "text": 3},
        {"player": "ada", "text": "hi", "to": "bo"},
    ],
    ids=["no text", "text is no string", "extra field"],
)
def test_message_event_of_another_shape_stops_the_match(data):
    class Mumbles(SequentialCounter):
        def setup(self, state, ctx):
            ctx.emit(MESSAGE, data)

    plugin = Mumbles()

    with pytest.raises(PluginError, match="emitted a message event whose data is not"):
        play(plugin, random_bots(plugin, PLAYERS, 1))


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


class NeverEnds(SequentialCounter):
    """Plays round after round: every turn makes progress, but the game is never over."""

    max_turns = 12

    def is_over(self, state):
        return False


def test_game_that_never_ends_is_stopped_at_its_turn_limit():
    plugin, stored = NeverEnds(), []

    async def sink(first_seq, events):
        stored.extend(events)

    match = Match(plugin, random_bots(plugin, PLAYERS, 1), seed=1, sink=sink)

    with pytest.raises(PluginError, match=r"counter is not over after 12 turns \(max_turns\)"):
        asyncio.run(run_to_turn_limit(match))

    # Twelve turns were played, and the log says why there is no thirteenth.
    assert types(match).count("action_accepted") == 12
    assert match.state.clock == 6
    last = match.events[-1]
    assert (last.source, last.type) == (EventSource.ENGINE, "turn_limit_reached")
    assert last.data == {"max_turns": 12}
    assert last.visible_to == ()
    assert stored == match.events
    assert "match_finished" not in types(match)


@pytest.mark.parametrize(
    ("plugin_class", "needed"),
    [(SequentialCounter, 4), (SimultaneousCounter, 2), (TickCounter, 2)],
)
def test_turn_limit_can_be_set_for_one_match(plugin_class, needed):
    plugin = plugin_class()  # two rounds take `needed` turns

    def match(max_turns):
        return Match(
            plugin,
            random_bots(plugin, PLAYERS, 1),
            seed=1,
            settings={"rounds": 2},
            max_turns=max_turns,
        )

    # A match that needs exactly as many turns as allowed finishes.
    exact = match(needed)
    asyncio.run(exact.run())
    assert types(exact)[-1] == "match_finished"

    short = match(needed - 1)
    with pytest.raises(PluginError, match=f"not over after {needed - 1} turns"):
        asyncio.run(short.run())
    assert short.events[-1].data == {"max_turns": needed - 1}
    assert short.events[:-1] == exact.events[: len(short.events) - 1]


def test_game_without_a_limit_of_its_own_gets_the_default():
    assert SequentialCounter.max_turns == 10_000
