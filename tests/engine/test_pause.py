"""Pausing a match: an agent says it cannot go on without the user, and the match waits."""

import asyncio

import pytest

from arena.agents.random_bot import random_bots
from arena.engine.match import Match
from arena.engine.replay import replay
from arena.engine.types import AgentError, EventSource, MatchPaused

from .counter_game import Scripted, SequentialCounter, SimultaneousCounter, add

PLAYERS = ["ada", "bo"]
CAP_REACHED = MatchPaused("match_cap", spent_micro_eur=480, cap_micro_eur=500)


def types(match):
    return [event.type for event in match.events]


def game_events(match):
    return [event for event in match.events if event.source is EventSource.GAME]


def run_until_pause(match):
    """Run a match that must pause. Returns the pause."""
    with pytest.raises(MatchPaused) as pause:
        asyncio.run(match.run())
    return pause.value


class PausesOnce:
    """Plays like `agent`, but pauses the match instead of answering request number `at`."""

    def __init__(self, agent, at):
        self._agent = agent
        self._at = at
        self._asked = 0

    async def act(self, request):
        self._asked += 1
        if self._asked == self._at:
            raise CAP_REACHED
        return await self._agent.act(request)


def test_match_pauses_when_an_agent_cannot_go_on_without_the_user():
    agents = {"ada": Scripted(add(1)), "bo": Scripted(CAP_REACHED)}
    match = Match(SequentialCounter(), agents, seed=1)

    pause = run_until_pause(match)

    assert pause is CAP_REACHED
    assert types(match) == ["match_started", "action_accepted", "added", "match_paused"]
    paused = match.events[-1]
    assert paused.source is EventSource.ENGINE
    assert paused.data == {"reason": "match_cap", "spent_micro_eur": 480, "cap_micro_eur": 500}
    assert paused.visible_to == ()
    assert match.state.amounts == {"ada": [1], "bo": []}


def test_paused_match_continues_with_the_turn_that_was_not_played():
    ada = Scripted(add(1), add(2))
    # Bo's first try is illegal, and the correction runs into the pause.
    bo = Scripted(add(0), CAP_REACHED, add(2), add(3))
    match = Match(SequentialCounter(), {"ada": ada, "bo": bo}, seed=1)

    async def scenario():
        with pytest.raises(MatchPaused):
            await match.run()
        return await match.run()

    placements = asyncio.run(scenario())

    # The paused turn left no trace: not even bo's rejected try is in the log.
    assert types(match) == [
        "match_started",
        "action_accepted",
        "added",
        "match_paused",
        "match_resumed",
        "action_accepted",
        "added",
        "round_closed",
        "action_accepted",
        "added",
        "action_accepted",
        "added",
        "round_closed",
        "match_finished",
    ]
    assert match.events[4].visible_to == ()
    assert match.state.amounts == {"ada": [1, 2], "bo": [2, 3]}
    assert [p.player for p in placements if p.rank == 1] == ["bo"]
    # Bo is asked for the same turn again and sees nothing of the pause.
    assert bo.requests[2] == bo.requests[0]


def test_pause_does_not_change_a_sequential_game():
    plugin, settings = SequentialCounter(), {"rounds": 6}

    def play(pause_at):
        bots = random_bots(plugin, PLAYERS, 5)
        agents = {"ada": bots["ada"], "bo": PausesOnce(bots["bo"], pause_at)}
        match = Match(plugin, agents, seed=5, settings=settings)

        async def scenario():
            if pause_at:
                with pytest.raises(MatchPaused):
                    await match.run()
            await match.run()

        asyncio.run(scenario())
        return match

    straight, paused, paused_again = play(None), play(4), play(4)

    assert "match_paused" in types(paused)
    assert game_events(paused) == game_events(straight)
    assert paused.state == straight.state
    assert paused.events == paused_again.events


def test_pause_is_stored_and_the_stored_log_replays():
    plugin, stored = SequentialCounter(), []

    async def sink(first_seq, events):
        assert first_seq == len(stored)
        stored.extend(events)

    agents = {"ada": Scripted(add(1)), "bo": Scripted(add(0), CAP_REACHED)}
    match = Match(plugin, agents, seed=1, sink=sink)

    run_until_pause(match)

    assert stored == match.events
    assert stored[-1].type == "match_paused"
    assert replay(plugin, stored) == match.state


def test_pause_stops_the_other_players_of_the_turn():
    class Waits:
        stopped = False

        async def act(self, request):
            try:
                await asyncio.Event().wait()
            finally:
                self.stopped = True

    ada = Waits()
    match = Match(SimultaneousCounter(), {"ada": ada, "bo": Scripted(CAP_REACHED)}, seed=1)

    async def scenario():
        with pytest.raises(MatchPaused):
            await match.run()
        return ada.stopped

    # Ada's model is not left busy with a turn that is dropped.
    assert asyncio.run(scenario()) is True
    assert types(match) == ["match_started", "match_paused"]


def test_seat_that_failed_in_a_paused_turn_is_asked_again():
    gave_up = AgentError("model call failed after 4 tries (Timeout)")
    ada = Scripted(gave_up, add(1), add(2))
    bo = Scripted(CAP_REACHED, add(1), add(2))
    match = Match(SimultaneousCounter(), {"ada": ada, "bo": bo}, seed=1)

    async def scenario():
        with pytest.raises(MatchPaused):
            await match.run()
        await match.run()

    asyncio.run(scenario())

    # The turn in which ada failed was dropped with its events, so the failure
    # does not count: nothing in the log would explain a random seat.
    assert "agent_failed" not in types(match)
    assert "action_fallback" not in types(match)
    assert match.state.amounts == {"ada": [1, 2], "bo": [1, 2]}


def test_match_can_pause_more_than_once():
    bo = Scripted(CAP_REACHED, MatchPaused("month_cap"))
    match = Match(SequentialCounter(), {"ada": Scripted(add(1), add(2)), "bo": bo}, seed=1)

    async def scenario():
        reasons = []
        for _ in range(2):
            with pytest.raises(MatchPaused) as pause:
                await match.run()
            reasons.append(pause.value.reason)
        return reasons

    assert asyncio.run(scenario()) == ["match_cap", "month_cap"]
    assert types(match)[3:] == ["match_paused", "match_resumed", "match_paused"]


def test_finished_match_cannot_run_again():
    plugin = SequentialCounter()
    match = Match(plugin, random_bots(plugin, PLAYERS, 1), seed=1)
    asyncio.run(match.run())
    events = list(match.events)

    with pytest.raises(RuntimeError, match="already been played"):
        asyncio.run(match.run())

    assert match.events == events
