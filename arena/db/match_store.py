"""Stores which matches exist and how they ended. Their events are in the event store."""

from collections.abc import Sequence
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

import asyncpg
from pydantic import BaseModel

from arena.engine.types import Placement, PlayerId

Status = Literal["running", "finished", "failed", "interrupted", "aborted"]

_COLUMNS = "id, game, status, players, seed, settings, started_at, finished_at, placements, memory"


class MatchRecord(BaseModel):
    id: UUID
    game: str
    status: Status
    players: list[PlayerId]
    seed: int
    settings: dict[str, Any]
    started_at: datetime
    finished_at: datetime | None
    placements: list[Placement] | None
    memory: bool = True  # False: the match neither reads nor writes memory


class MatchStore:
    def __init__(self, pool: asyncpg.Pool):
        self._pool = pool

    async def create(
        self,
        match_id: UUID,
        game: str,
        players: Sequence[PlayerId],
        seed: int,
        settings: dict[str, Any],
        *,
        memory: bool = True,
    ) -> MatchRecord:
        """Record a match that starts now, with status `running`."""
        row = await self._pool.fetchrow(
            "INSERT INTO matches (id, game, status, players, seed, settings, memory) "
            f"VALUES ($1, $2, 'running', $3, $4, $5, $6) RETURNING {_COLUMNS}",
            match_id,
            game,
            list(players),
            seed,
            settings,
            memory,
        )
        return MatchRecord(**row)

    async def close(
        self, match_id: UUID, status: Status, placements: Sequence[Placement] | None = None
    ) -> None:
        """Record how a match stopped. A match that is no longer running keeps its record."""
        await self._pool.execute(
            "UPDATE matches SET status = $2, placements = $3, finished_at = now() "
            "WHERE id = $1 AND status = 'running'",
            match_id,
            status,
            None if placements is None else [p.model_dump() for p in placements],
        )

    async def interrupt_running(self) -> None:
        """Close every match that is still marked as running.

        For the start of the server: a match runs inside one server process, so
        whatever an earlier process left running will never finish.
        """
        await self._pool.execute(
            "UPDATE matches SET status = 'interrupted', finished_at = now() "
            "WHERE status = 'running'"
        )

    async def get(self, match_id: UUID) -> MatchRecord | None:
        row = await self._pool.fetchrow(f"SELECT {_COLUMNS} FROM matches WHERE id = $1", match_id)
        return None if row is None else MatchRecord(**row)

    async def finished_with_cost(self, limit: int = 100) -> list[tuple[MatchRecord, int]]:
        """The newest finished matches, newest first, each with its model cost in micro-euros."""
        rows = await self._pool.fetch(
            f"SELECT {_COLUMNS}, coalesce(c.cost, 0) AS cost FROM matches "
            "LEFT JOIN (SELECT match_id, sum(cost_micro_eur) AS cost FROM model_calls "
            "GROUP BY match_id) c ON c.match_id = matches.id "
            "WHERE status = 'finished' ORDER BY finished_at DESC, id LIMIT $1",
            limit,
        )
        return [
            (MatchRecord(**{k: v for k, v in row.items() if k != "cost"}), int(row["cost"]))
            for row in rows
        ]

    async def recent(self, statuses: Sequence[Status] | None = None) -> list[MatchRecord]:
        """The newest 100 matches, newest first; only those in `statuses` if given."""
        rows = await self._pool.fetch(
            f"SELECT {_COLUMNS} FROM matches WHERE $1::text[] IS NULL OR status = ANY($1) "
            "ORDER BY started_at DESC, id LIMIT 100",
            None if statuses is None else list(statuses),
        )
        return [MatchRecord(**row) for row in rows]
