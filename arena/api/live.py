"""Matches that run inside the API process, and the event stream spectators follow."""

import asyncio
import logging
import random
from collections.abc import AsyncIterator, Mapping, Sequence
from typing import Any
from uuid import UUID, uuid4

import asyncpg

from arena.agents.random_bot import random_bots
from arena.db.event_store import EventStore
from arena.db.match_store import MatchRecord, MatchStore
from arena.engine.match import Match
from arena.engine.plugin import GamePlugin
from arena.engine.types import Event, Placement
from arena.ratings.store import RatingStore

log = logging.getLogger(__name__)

MAX_RUNNING = 10  # matches this server plays at the same time


class ArenaBusy(Exception):
    """The server already plays as many matches as it does at a time."""


class _Running:
    """A match of this process and how much of its log spectators may read."""

    def __init__(self, match: Match):
        self.match = match
        self.published = 0  # events of completed turns, all of them stored
        self.over = False
        self.changed = asyncio.Condition()

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

    def __init__(self, pool: asyncpg.Pool, games: Mapping[str, GamePlugin]):
        self.games = games
        self.matches = MatchStore(pool)
        self._events = EventStore(pool)
        self._ratings = RatingStore(pool)
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
    ) -> MatchRecord:
        """Start a match of random bots and return its record. It plays on in the background.

        Between two turns the match waits `turn_delay` seconds, so that
        people can follow it. Raises ValueError for a player count or settings
        the game refuses, and ArenaBusy while MAX_RUNNING matches are running.
        """
        match_id = uuid4()
        if seed is None:
            seed = random.SystemRandom().randrange(2**31)

        async def sink(first_seq: int, events: Sequence[Event]) -> None:
            if first_seq:
                await asyncio.sleep(turn_delay)
            await self._events.append(match_id, first_seq, events)
            await running.publish(first_seq + len(events))

        match = Match(
            plugin, random_bots(plugin, players, seed), seed=seed, settings=settings, sink=sink
        )
        if len(self._running) >= MAX_RUNNING:
            raise ArenaBusy(
                f"{MAX_RUNNING} matches are running, the most this server plays at a time. "
                "Try again when one has ended."
            )
        running = _Running(match)
        # The place is taken before the first await, so two requests cannot share the last one.
        self._running[match_id] = running
        try:
            record = await self.matches.create(match_id, plugin.id, players, seed, match.settings)
        except BaseException:
            del self._running[match_id]
            raise
        task = asyncio.create_task(self._play(match_id, running))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return record

    async def _play(self, match_id: UUID, running: _Running) -> None:
        try:
            placements = await running.match.run()
            await self.matches.close(match_id, "finished", placements)
            await self._rate(match_id, running.match.plugin.id, placements)
        except Exception:
            log.exception("Match %s failed", match_id)
            await self.matches.close(match_id, "failed")
        finally:
            del self._running[match_id]
            await running.publish()

    async def _rate(self, match_id: UUID, game_id: str, placements: Sequence[Placement]) -> None:
        """Rate the bots of a finished match. A rating problem never fails the match."""
        try:
            profiles = await self._ratings.bot_profiles([p.player for p in placements])
            await self._ratings.apply_match_result(
                match_id,
                game_id,
                [Placement(player=str(profiles[p.player]), rank=p.rank) for p in placements],
            )
        except Exception:
            log.exception("Rating of match %s failed", match_id)

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
