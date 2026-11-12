"""Stores which matches exist and how they ended. Their events are in the event store."""

from collections.abc import Sequence
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

import asyncpg
from pydantic import BaseModel, ConfigDict, Field, model_validator

from arena.engine.types import Placement, PlayerId
from arena.ratings.store import BOT_MODEL_ID
from arena.transcript.common import display_names

Status = Literal["running", "finished", "failed", "interrupted", "aborted"]
Origin = Literal["played", "imported"]


class Seat(BaseModel):
    """Who played a seat, for the people who watch: the event log only knows the seat id."""

    name: str
    model_id: str | None = None  # an id from config/models.yaml; None for a bot
    kind: Literal["model", "bot"]
    personality: str | None = None  # a personality id of config/personalities, if one was set


def bot_seats(players: Sequence[PlayerId]) -> dict[PlayerId, Seat]:
    return {player: Seat(name=f"Random Bot {player}", kind="bot") for player in players}


class Batch(BaseModel):
    """The batch a match was played in: an experiment stage, a league, any run of matches."""

    model_config = ConfigDict(extra="forbid")  # a misspelt key fails loudly

    id: str = Field(
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$",
        description='Stable id of the batch, e.g. "E1-A2"; GET /matches?batch= filters by it',
    )
    label: str = Field(min_length=1, max_length=120, description="What people read")
    index: int | None = Field(None, ge=1, description="This match's place in the batch, from 1")
    of: int | None = Field(None, ge=1, description="How many matches the batch plans")
    budget_eur: float | None = Field(None, ge=0, description="What the whole batch may spend")

    @model_validator(mode="after")
    def _within(self) -> "Batch":
        if self.index is not None and self.of is not None and self.index > self.of:
            raise ValueError(f"index {self.index} is beyond of {self.of}")
        return self


_COLUMNS = (
    "id, game, status, players, seed, settings, started_at, finished_at, placements, seats, "
    "origin, memory, prompt_version, batch"
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
    memory: bool = True  # False: the match neither reads nor writes memory
    prompt_version: str | None = None  # None for matches recorded before it was
    batch: Batch | None = None  # None for a match played on its own

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
        memory: bool = True,
        prompt_version: str | None = None,
        batch: Batch | None = None,
    ) -> MatchRecord:
        """Record a match that starts now, with status `running`."""
        row = await self._pool.fetchrow(
            "INSERT INTO matches (id, game, status, players, seed, settings, seats, origin, "
            "memory, prompt_version, batch) "
            f"VALUES ($1, $2, 'running', $3, $4, $5, $6, $7, $8, $9, $10) RETURNING {_COLUMNS}",
            match_id,
            game,
            list(players),
            seed,
            settings,
            None if seats is None else {p: s.model_dump() for p, s in seats.items()},
            origin,
            memory,
            prompt_version,
            None if batch is None else batch.model_dump(),
        )
        return MatchRecord(**row)

    async def tag_batch(self, match_id: UUID, batch: Batch) -> Literal["tagged", "same", "other"]:
        """Put a match played without a batch into one; a match is never moved to another.

        "tagged" when it had none, "same" when it already had this batch, "other"
        when it has a different one (left as it is). KeyError: no such match.
        """
        async with self._pool.acquire() as connection, connection.transaction():
            before = await connection.fetchrow(
                "SELECT batch FROM matches WHERE id = $1 FOR UPDATE", match_id
            )
            if before is None:
                raise KeyError(match_id)
            if before["batch"] is not None:
                return "same" if before["batch"] == batch.model_dump() else "other"
            await connection.execute(
                "UPDATE matches SET batch = $2 WHERE id = $1", match_id, batch.model_dump()
            )
            return "tagged"

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
        """How each seat of a rated match is shown: a bot as "Random Bot p3", a model as its
        profile name, with "(model)" added when the name says more than the model id (a model
        with a personality). Empty for a match that was not rated."""
        profiles = await self.seat_profiles(match_id)
        return {
            seat: name if model in (BOT_MODEL_ID, name) else f"{name} ({model})"
            for seat, (name, model) in profiles.items()
        }

    async def display_names(self, record: MatchRecord) -> dict[str, str]:
        """The name shown for each seat everywhere (see `arena.transcript.common.display_names`).

        From the match record's seats; a match recorded before seats were kept falls back to
        its profile labels, else the seat id.
        """
        if record.seats:
            return display_names({p: (s.kind, s.name) for p, s in record.seats.items()})
        return {**{p: p for p in record.players}, **await self.seat_names(record.id)}

    async def finished(self, limit: int = 100) -> list[MatchRecord]:
        """The newest finished matches, newest first."""
        rows = await self._pool.fetch(
            f"SELECT {_COLUMNS} FROM matches WHERE status = 'finished' "
            "ORDER BY finished_at DESC, id LIMIT $1",
            limit,
        )
        return [MatchRecord(**row) for row in rows]

    async def unrated_model_matches(self) -> list[MatchRecord]:
        """Finished matches with a result and a model in a seat that no rating has counted.

        Oldest first, the order ratings must be applied in.
        """
        rows = await self._pool.fetch(
            f"SELECT {_COLUMNS} FROM matches m WHERE status = 'finished' "
            "AND placements IS NOT NULL "
            "AND NOT EXISTS (SELECT 1 FROM rated_matches r WHERE r.match_id = m.id) "
            "AND EXISTS (SELECT 1 FROM jsonb_each(seats) seat WHERE seat.value->>'kind' = 'model') "
            "ORDER BY started_at, id"
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

    async def recent(
        self,
        statuses: Sequence[Status] | None = None,
        batch: str | None = None,
        game: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[MatchRecord]:
        """Matches, newest first; only those in `statuses`, of `game` and of `batch` if given.

        `limit` defaults to 100, or 1000 for a batch; `offset` skips that many newer matches.
        """
        rows = await self._pool.fetch(
            f"SELECT {_COLUMNS} FROM matches WHERE ($1::text[] IS NULL OR status = ANY($1)) "
            "AND ($2::text IS NULL OR batch->>'id' = $2) AND ($3::text IS NULL OR game = $3) "
            "ORDER BY started_at DESC, id LIMIT $4 OFFSET $5",
            None if statuses is None else list(statuses),
            batch,
            game,
            limit if limit is not None else (100 if batch is None else 1000),
            offset,
        )
        return [MatchRecord(**row) for row in rows]

    async def count(
        self,
        statuses: Sequence[Status] | None = None,
        batch: str | None = None,
        game: str | None = None,
    ) -> int:
        """How many matches `recent` would list without its limit."""
        return await self._pool.fetchval(
            "SELECT count(*) FROM matches WHERE ($1::text[] IS NULL OR status = ANY($1)) "
            "AND ($2::text IS NULL OR batch->>'id' = $2) AND ($3::text IS NULL OR game = $3)",
            None if statuses is None else list(statuses),
            batch,
            game,
        )
