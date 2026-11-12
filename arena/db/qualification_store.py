"""Stores qualification jobs and their results (table `qualifications`)."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from uuid import UUID

import asyncpg
from pydantic import BaseModel, Field

COLUMNS = (
    "id, model_id, game, scope, config_hash, configuration, status, badge, reasons, cases, "
    "counts, reserved_micro_eur, cap_micro_eur, parent_id, started_at, finished_at, expires_at"
)


class Qualification(BaseModel):
    id: UUID
    model_id: str
    game: str
    scope: str
    config_hash: str
    configuration: dict[str, Any]
    status: str = Field(description="running, qualified, unqualified or unknown")
    badge: str | None = Field(description='"repaired (v1)" on a qualified repair-enabled job')
    reasons: list[str]
    cases: list[dict[str, Any]]
    counts: dict[str, int] = Field(description="Cases clean, repaired, failed and unknown")
    reserved_micro_eur: int
    cap_micro_eur: int
    parent_id: UUID | None
    started_at: datetime
    finished_at: datetime | None
    expires_at: datetime | None


class QualificationStore:
    def __init__(self, pool: asyncpg.Pool):
        self._pool = pool

    async def start(
        self,
        id: UUID,
        *,
        model_id: str,
        game: str,
        scope: str,
        config_hash: str,
        configuration: dict[str, Any],
        reserved_micro_eur: int,
        cap_micro_eur: int,
        parent_id: UUID | None,
        now: datetime,
    ) -> None:
        await self._pool.execute(
            "INSERT INTO qualifications (id, model_id, game, scope, config_hash, configuration,"
            " status, reserved_micro_eur, cap_micro_eur, parent_id, started_at)"
            " VALUES ($1, $2, $3, $4, $5, $6::jsonb, 'running', $7, $8, $9, $10)",
            id,
            model_id,
            game,
            scope,
            config_hash,
            json.dumps(configuration),
            reserved_micro_eur,
            cap_micro_eur,
            parent_id,
            now,
        )

    async def finish(
        self,
        id: UUID,
        *,
        status: str,
        badge: str | None,
        reasons: list[str],
        cases: list[dict[str, Any]],
        counts: dict[str, int],
        now: datetime,
        expires_at: datetime,
    ) -> None:
        await self._pool.execute(
            "UPDATE qualifications SET status = $2, badge = $3, reasons = $4::jsonb,"
            " cases = $5::jsonb, counts = $6::jsonb, finished_at = $7, expires_at = $8"
            " WHERE id = $1",
            id,
            status,
            badge,
            json.dumps(reasons),
            json.dumps(cases),
            json.dumps(counts),
            now,
            expires_at,
        )

    async def get(self, id: UUID) -> Qualification | None:
        row = await self._pool.fetchrow(f"SELECT {COLUMNS} FROM qualifications WHERE id = $1", id)
        return None if row is None else _record(row)

    async def recent(
        self, model_id: str | None = None, game: str | None = None, limit: int = 50
    ) -> list[Qualification]:
        rows = await self._pool.fetch(
            f"SELECT {COLUMNS} FROM qualifications"
            " WHERE ($1::text IS NULL OR model_id = $1) AND ($2::text IS NULL OR game = $2)"
            " ORDER BY started_at DESC LIMIT $3",
            model_id,
            game,
            limit,
        )
        return [_record(row) for row in rows]

    async def interrupt_running(self, now: datetime) -> None:
        """A job an earlier process left running ended with it: its result is unknown."""
        await self._pool.execute(
            "UPDATE qualifications SET status = 'unknown',"
            " reasons = '[\"interrupted: the arena stopped during the job\"]'::jsonb,"
            " finished_at = $1 WHERE status = 'running'",
            now,
        )


def _record(row: asyncpg.Record) -> Qualification:
    data = dict(row)
    for key in ("configuration", "reasons", "cases", "counts"):
        if isinstance(data[key], str):
            data[key] = json.loads(data[key])
    return Qualification(**data)
