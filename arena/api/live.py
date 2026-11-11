"""Matches that run inside the API process, and the event stream spectators follow."""

import asyncio
import logging
import random
from collections.abc import AsyncIterator, Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

import asyncpg

from arena.agents.budget import Budget
from arena.agents.random_bot import random_bots
from arena.agents.runner import ModelAgent
from arena.catalog import resolve
from arena.config import display_name, load_config
from arena.db.event_store import EventStore
from arena.db.ledger import Ledger
from arena.db.match_store import MatchRecord, MatchStore, Seat, bot_seats
from arena.engine.match import Match
from arena.engine.plugin import GamePlugin
from arena.engine.types import Event, MatchPaused, Placement
from arena.memory.store import MemoryStore
from arena.ratings.store import RatingStore

log = logging.getLogger(__name__)

MAX_RUNNING = 10  # matches this server plays at the same time


class ArenaBusy(Exception):
    """The server already plays as many matches as it does at a time."""


class NotRunning(Exception):
    """The match is not being played by this server (it ended, or never ran here)."""


@dataclass(frozen=True)
class Control:
    """How a running match is being played right now."""

    paused: bool
    turn_delay: float


class _Running:
    """A match of this process and how much of its log spectators may read."""

    def __init__(self, match: Match, turn_delay: float):
        self.match = match
        self.published = 0  # events of completed turns, all of them stored
        self.over = False
        self.changed = asyncio.Condition()
        self.turn_delay = turn_delay
        self.resumed = asyncio.Event()  # cleared while paused
        self.resumed.set()
        self.aborted = False
        self.finished = False  # its match_finished is stored; it can no longer be aborted
        self.task: asyncio.Task | None = None
        self.memory = True  # False: a fair benchmark, nothing is remembered
        self._delay_changed = asyncio.Event()

    def control(self) -> Control:
        return Control(paused=not self.resumed.is_set(), turn_delay=self.turn_delay)

    async def wait_delay(self) -> None:
        """Wait `turn_delay` seconds from now, the delay as it is set when it runs out."""
        loop = asyncio.get_running_loop()
        since = loop.time()
        while (left := since + self.turn_delay - loop.time()) > 0:
            self._delay_changed.clear()
            with suppress(TimeoutError):
                await asyncio.wait_for(self._delay_changed.wait(), left)

    def set_delay(self, turn_delay: float) -> None:
        self.turn_delay = turn_delay
        self._delay_changed.set()

    async def publish(self, count: int | None = None) -> None:
        """Make the first `count` events readable; without a count, say that no more will come."""
        async with self.changed:
            if count is None:
                self.over = True
            else:
                self.published = count
            self.changed.notify_all()


class LiveMatches:
    """Starts matches as tasks of the server process, stores them and streams their events."""

    def __init__(self, pool: asyncpg.Pool, games: Mapping[str, GamePlugin], ledger: Ledger):
        self.games = games
        self.matches = MatchStore(pool)
        self._events = EventStore(pool)
        self.ledger = ledger
        self._ratings = RatingStore(pool)
        self._memory = MemoryStore(pool)
        self._running: dict[UUID, _Running] = {}
        self._tasks: set[asyncio.Task] = set()

    async def start(
        self,
        plugin: GamePlugin,
        players: Sequence[str],
        *,
        seed: int | None,
        settings: Mapping[str, Any],
        turn_delay: float,
        models: Mapping[str, str] | None = None,
        memory: bool = True,
    ) -> MatchRecord:
        """Start a match and return its record. It plays on in the background.

        Every seat is a random bot, or with `models` (seat -> model id from
        config/models.yaml) the model of that seat, behind one Budget for the
        match: every call is booked before it is sent, and a call that would
        pass a cap is not sent and ends the match as `interrupted`. A match
        with models starts only when the ledger answers and is the one earlier
        model matches were booked in (LedgerUnavailable otherwise).

        Between two turns the match waits `turn_delay` seconds, so that
        people can follow it. Raises ValueError for a player count or settings
        the game refuses, and ArenaBusy while MAX_RUNNING matches are running.
        """
        match_id = uuid4()
        if seed is None:
            seed = random.SystemRandom().randrange(2**31)

        async def sink(first_seq: int, events: Sequence[Event]) -> None:
            if first_seq:
                await running.wait_delay()
            await self._events.append(match_id, first_seq, events)
            if any(event.type == "match_finished" for event in events):
                running.finished = True  # stored: the match is over, whatever comes now
            await running.publish(first_seq + len(events))
            if not running.finished:
                await running.resumed.wait()  # a paused match stops here, between two turns

        if models is None:
            agents = random_bots(plugin, players, seed)
            seats = bot_seats(players)
        else:
            await self.ledger.check(await self.matches.model_matches())
            config = await resolve(load_config(), models.values())
            budget = Budget(self.ledger, match_id, config)
            agents = {
                seat: ModelAgent(budget.model(seat, models[seat]), plugin, settings=settings)
                for seat in players
            }
            seats = {
                seat: Seat(
                    name=display_name(config, models[seat]), model_id=models[seat], kind="model"
                )
                for seat in players
            }
        match = Match(plugin, agents, seed=seed, settings=settings, sink=sink)
        if len(self._running) >= MAX_RUNNING:
            raise ArenaBusy(
                f"{MAX_RUNNING} matches are running, the most this server plays at a time. "
                "Try again when one has ended."
            )
        running = _Running(match, turn_delay)
        running.memory = memory
        # The place is taken before the first await, so two requests cannot share the last one.
        self._running[match_id] = running
        try:
            record = await self.matches.create(
                match_id,
                plugin.id,
                players,
                seed,
                match.settings,
                seats=seats,
                memory=memory,
                prompt_version=plugin.prompt_version(match.settings),
            )
        except BaseException:
            del self._running[match_id]
            raise
        task = asyncio.create_task(self._play(match_id, running, rated=models is None))
        running.task = task
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return record

    async def _play(self, match_id: UUID, running: _Running, *, rated: bool) -> None:
        try:
            placements = await running.match.run()
            await self.matches.close(match_id, "finished", placements)
            if rated:  # bots only until model profiles reach the API (D-082)
                await self._rate(match_id, running.match, placements, memory=running.memory)
        except MatchPaused as pause:
            # Nobody here can allow more money: a cap ends the match. Its log says why.
            log.warning("Match %s stopped at a cost cap (%s)", match_id, pause.reason)
            await self.matches.close(match_id, "interrupted")
        except asyncio.CancelledError:
            if not running.aborted:
                raise  # the server shuts down: the next start marks the match interrupted
            await self.matches.close(match_id, "aborted")
        except Exception:
            log.exception("Match %s failed", match_id)
            await self.matches.close(match_id, "failed")
        finally:
            del self._running[match_id]
            await running.publish()

    def _get(self, match_id: UUID) -> _Running:
        running = self._running.get(match_id)
        if running is None:
            raise NotRunning("The match is not running, so it cannot be controlled.")
        return running

    def control(self, match_id: UUID) -> Control:
        """Whether a running match is paused, and its delay between turns."""
        return self._get(match_id).control()

    def pause(self, match_id: UUID) -> Control:
        """Stop the match after its current turn, until `resume`."""
        running = self._get(match_id)
        running.resumed.clear()
        return running.control()

    def resume(self, match_id: UUID) -> Control:
        running = self._get(match_id)
        running.resumed.set()
        return running.control()

    def set_delay(self, match_id: UUID, turn_delay: float) -> Control:
        """Seconds to wait after each turn, from now on: also a wait that has begun follows it."""
        running = self._get(match_id)
        running.set_delay(turn_delay)
        return running.control()

    async def abort(self, match_id: UUID) -> None:
        """Stop the match for good. Its log stays; its record says `aborted`."""
        running = self._get(match_id)
        if running.finished:
            raise NotRunning("The match has ended, so it cannot be aborted.")
        running.aborted = True
        running.resumed.set()
        assert running.task is not None
        running.task.cancel()
        await asyncio.gather(running.task, return_exceptions=True)

    async def _rate(
        self, match_id: UUID, match: Match, placements: Sequence[Placement], *, memory: bool
    ) -> None:
        """Rate the bots of a finished match and, unless memory is off, remember it.

        A rating or memory problem never fails the match.
        """
        game_id = match.plugin.id
        try:
            profiles = await self._ratings.bot_profiles([p.player for p in placements])
            await self._ratings.apply_match_result(
                match_id,
                game_id,
                [Placement(player=str(profiles[p.player]), rank=p.rank) for p in placements],
                seats=profiles,
            )
        except Exception:
            log.exception("Rating of match %s failed", match_id)
            return
        if not memory:
            return
        try:
            await self._memory.remember_match(
                match_id, game_id, match.events, profiles, game_name=match.plugin.name
            )
        except Exception:
            log.exception("Remembering match %s failed", match_id)

    async def log(self, match_id: UUID) -> list[Event]:
        """The log of a match so far: its completed turns."""
        return await self._events.load(match_id)

    async def events(self, match_id: UUID) -> AsyncIterator[tuple[int, Event]]:
        """The log of a match from its first event, with positions.

        For a match that is still being played, the stream waits for each new
        turn and ends when the match stops. Only completed turns are shown.
        """
        running = self._running.get(match_id)
        if running is None:
            for seq, event in enumerate(await self.log(match_id)):
                yield seq, event
            return
        seq = 0
        while True:
            async with running.changed:
                while running.published == seq and not running.over:
                    await running.changed.wait()
                ready = running.match.events[seq : running.published]
            if not ready:
                return
            for event in ready:
                yield seq, event
                seq += 1

    async def stop(self) -> None:
        """Stop every running match. For the shutdown of the server.

        Their records stay `running` until the next start marks them as interrupted.
        """
        tasks = list(self._tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
