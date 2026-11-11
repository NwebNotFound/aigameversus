"""Stores match event logs in Postgres."""

from collections.abc import Sequence
from uuid import UUID

import asyncpg

from arena.engine.types import Event


class EventStore:
    def __init__(self, pool: asyncpg.Pool):
        self._pool = pool

    async def append(self, match_id: UUID, first_seq: int, events: Sequence[Event]) -> None:
        """Add events at positions `first_seq`, `first_seq + 1`, ... of a match log.

        All or nothing. Raises `asyncpg.UniqueViolationError` if a position is
        already taken, which means two writers for one match.
        """
        rows = [
            (
                match_id,
                first_seq + offset,
                event.source.value,
                event.type,
                event.data,
                None if event.visible_to is None else list(event.visible_to),
            )
            for offset, event in enumerate(events)
        ]
        # executemany is atomic: either every row is stored or none.
        await self._pool.executemany(
            "INSERT INTO match_events (match_id, seq, source, type, data, visible_to) "
            "VALUES ($1, $2, $3, $4, $5, $6)",
            rows,
        )

    async def load(self, match_id: UUID) -> list[Event]:
        """The whole log of a match in order. Empty if the match is unknown."""
        rows = await self._pool.fetch(
            "SELECT source, type, data, visible_to FROM match_events "
            "WHERE match_id = $1 ORDER BY seq",
            match_id,
        )
        return [
            Event(
                source=row["source"],
                type=row["type"],
                data=row["data"],
                visible_to=None if row["visible_to"] is None else tuple(row["visible_to"]),
            )
            for row in rows
        ]
