"""Stores which matches exist and how they ended. Their events are in the event store."""

from collections.abc import Sequence
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

import asyncpg
from pydantic import BaseModel

from arena.engine.types import Placement, PlayerId

Status = Literal["running", "finished", "failed", "interrupted", "aborted"]
Origin = Literal["played", "imported"]


class Seat(BaseModel):
    """Who played a seat, for the people who watch: the event log only knows the seat id."""

    name: str
    model_id: str | None = None  # an id from config/models.yaml; None for a bot
    kind: Literal["model", "bot"]


def bot_seats(players: Sequence[PlayerId]) -> dict[PlayerId, Seat]:
    return {player: Seat(name=f"Random Bot {player}", kind="bot") for player in players}


_COLUMNS = (
    "id, game, status, players, seed, settings, started_at, finished_at, placements, seats, origin"
)


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
    seats: dict[PlayerId, Seat] | None = None  # None for matches recorded before seats were
    origin: Origin = "played"

    @property
    def real(self) -> bool:
        """Whether a model played any seat."""
        return any(seat.kind == "model" for seat in (self.seats or {}).values())


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
        seats: dict[PlayerId, Seat] | None = None,
        origin: Origin = "played",
    ) -> MatchRecord:
        """Record a match that starts now, with status `running`."""
        row = await self._pool.fetchrow(
            "INSERT INTO matches (id, game, status, players, seed, settings, seats, origin) "
            f"VALUES ($1, $2, 'running', $3, $4, $5, $6, $7) RETURNING {_COLUMNS}",
            match_id,
            game,
            list(players),
            seed,
            settings,
            None if seats is None else {p: s.model_dump() for p, s in seats.items()},
            origin,
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

    async def seat_profiles(self, match_id: UUID) -> dict[str, tuple[str, str]]:
        """(profile name, model id) for each seat of a rated match; empty if it was not rated."""
        rows = await self._pool.fetch(
            "SELECT s.seat, p.name, p.model_id FROM match_seats s "
            "JOIN player_profiles p ON p.id = s.profile_id WHERE s.match_id = $1 ORDER BY s.seat",
            match_id,
        )
        return {row["seat"]: (row["name"], row["model_id"]) for row in rows}

    async def seat_names(self, match_id: UUID) -> dict[str, str]:
        """ "Name (model)" for each seat of a rated match; empty for a match that was not rated."""
        profiles = await self.seat_profiles(match_id)
        return {seat: f"{name} ({model})" for seat, (name, model) in profiles.items()}

    async def finished(self, limit: int = 100) -> list[MatchRecord]:
        """The newest finished matches, newest first."""
        rows = await self._pool.fetch(
            f"SELECT {_COLUMNS} FROM matches WHERE status = 'finished' "
            "ORDER BY finished_at DESC, id LIMIT $1",
            limit,
        )
        return [MatchRecord(**row) for row in rows]

    async def model_matches(self) -> int:
        """How many finished matches played here had a model in a seat.

        Imported matches booked their calls in another ledger, if anywhere.
        """
        return await self._pool.fetchval(
            "SELECT count(*) FROM matches WHERE status = 'finished' AND origin = 'played' "
            "AND EXISTS "
            "(SELECT 1 FROM jsonb_each(seats) seat WHERE seat.value->>'kind' = 'model')"
        )

    async def recent(self, statuses: Sequence[Status] | None = None) -> list[MatchRecord]:
        """The newest 100 matches, newest first; only those in `statuses` if given."""
        rows = await self._pool.fetch(
            f"SELECT {_COLUMNS} FROM matches WHERE $1::text[] IS NULL OR status = ANY($1) "
            "ORDER BY started_at DESC, id LIMIT 100",
            None if statuses is None else list(statuses),
        )
        return [MatchRecord(**row) for row in rows]
