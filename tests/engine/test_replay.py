import asyncio

import pytest

from arena.agents.random_bot import random_bots
from arena.engine.match import Match, PluginError
from arena.engine.replay import ReplayError, replay

from .counter_game import Scripted, SequentialCounter, SimultaneousCounter, TickCounter, add

PLAYERS = ["ada", "bo"]


def bot_match(plugin, *, seed=5, sink=None):
    match = Match(plugin, random_bots(plugin, PLAYERS, seed), seed=seed, sink=sink)
    asyncio.run(match.run())
    return match


class Recorder:
    """An event sink that keeps every batch it receives."""

    def __init__(self):
        self.batches = []

    async def __call__(self, first_seq, events):
        self.batches.append((first_seq, list(events)))


@pytest.mark.parametrize("plugin_class", [SequentialCounter, SimultaneousCounter, TickCounter])
def test_replaying_the_log_rebuilds_the_exact_end_state(plugin_class):
    plugin = plugin_class()
    match = bot_match(plugin)

    assert replay(plugin, match.events) == match.state


def test_replaying_a_prefix_gives_the_state_at_that_point():
    plugin = SequentialCounter()
    match = bot_match(plugin)
    first_close = next(i for i, e in enumerate(match.events) if e.type == "round_closed")

    state = replay(plugin, match.events[:first_close])

    assert state.clock == 0
    assert state.waiting == []
    assert {player: len(amounts) for player, amounts in state.amounts.items()} == {
        "ada": 1,
        "bo": 1,
    }


def test_replay_needs_no_agents_and_ignores_rejected_attempts():
    plugin = SequentialCounter()
    agents = {"ada": Scripted(add(0), add(1), add(2)), "bo": Scripted(add(3), add(1))}
    match = Match(plugin, agents, seed=1)
    asyncio.run(match.run())

    assert any(event.type == "action_rejected" for event in match.events)
    assert replay(plugin, match.events) == match.state


def test_log_without_a_start_cannot_be_replayed():
    plugin = SequentialCounter()
    match = bot_match(plugin)

    for broken in ([], match.events[1:]):
        with pytest.raises(ReplayError, match="does not start with match_started"):
            replay(plugin, broken)


def test_log_of_another_game_or_version_cannot_be_replayed():
    class NewRules(SequentialCounter):
        version = "2"

    match = bot_match(SequentialCounter())

    with pytest.raises(ReplayError, match="recorded with counter version 1, but .* version 2"):
        replay(NewRules(), match.events)


def test_sink_receives_the_whole_log_in_order_one_batch_per_turn():
    recorder = Recorder()
    match = bot_match(SequentialCounter(), sink=recorder)

    received = [event for _, events in recorder.batches for event in events]
    assert received == match.events
    position = 0
    for first_seq, events in recorder.batches:
        assert first_seq == position
        position += len(events)
    # Start, then one batch per turn, then the finish.
    assert [event.type for event in recorder.batches[0][1]] == ["match_started"]
    assert [event.type for event in recorder.batches[1][1]] == ["action_accepted", "added"]
    assert [event.type for event in recorder.batches[-1][1]] == ["match_finished"]


def test_turn_that_fails_is_not_handed_to_the_sink():
    class BreaksInSecondRound(SequentialCounter):
        def step(self, state, ctx):
            if state.clock == 1 and not state.waiting:
                raise RuntimeError("rules crashed")
            super().step(state, ctx)

    recorder = Recorder()
    plugin = BreaksInSecondRound()
    match = Match(plugin, random_bots(plugin, PLAYERS, 5), seed=5, sink=recorder)

    with pytest.raises(RuntimeError, match="rules crashed"):
        asyncio.run(match.run())

    stored = [event for _, events in recorder.batches for event in events]
    assert stored == match.events[: len(stored)]
    # Bo's move of round 2 was applied in memory, but its turn never completed.
    assert [event.type for event in match.events[len(stored) :]] == ["action_accepted", "added"]
    # The stored log stops at the turn boundary before it.
    state = replay(plugin, stored)
    assert (state.clock, state.waiting) == (1, ["bo"])


@pytest.mark.parametrize(
    "data",
    [{"cards": (1, 2)}, {"scores": {1: "one"}}],
    ids=["tuple", "integer key"],
)
def test_event_data_that_json_would_change_stops_the_match(data):
    class EmitsOddData(SequentialCounter):
        def setup(self, state, ctx):
            ctx.emit("odd", data)

    plugin = EmitsOddData()

    with pytest.raises(PluginError, match="event 'odd' has data that JSON would change"):
        bot_match(plugin)
