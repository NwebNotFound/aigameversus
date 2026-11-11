"""The spend ledger: what model calls have cost, per match and per month."""

import asyncio
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from uuid import UUID

import asyncpg

from arena.db.database import migrate
from arena.engine.types import MatchPaused, PlayerId

_LEDGER_LOCK = 7_240_002  # advisory lock id: one booking at a time, across processes
_READ_TIMEOUT = 10  # seconds; a ledger that does not answer by then counts as unreachable


class LedgerUnavailable(Exception):
    """The ledger cannot be read: no model may be called, and no cost can be shown."""


@asynccontextmanager
async def _reading() -> AsyncIterator[None]:
    try:
        async with asyncio.timeout(_READ_TIMEOUT):
            yield
    except (OSError, TimeoutError, asyncpg.PostgresError, asyncpg.InterfaceError) as error:
        raise LedgerUnavailable(
            f"The spend ledger cannot be read ({type(error).__name__}). "
            "Check LEDGER_DATABASE_URL and that its database runs."
        ) from error


class Ledger:
    """Every model call that was sent, with its cost in millionths of a euro.

    A call is booked before it is sent, at the most it can cost, and corrected
    when the provider reports its tokens. A call that never reports (an error,
    a timeout, a crash) keeps its upper bound, so the sums can be too high but
    never too low.
    """

    def __init__(self, pool: asyncpg.Pool):
        self._pool = pool

    async def prepare(self) -> None:
        """Bring the ledger's schema up to date. Raises LedgerUnavailable."""
        async with _reading():
            await migrate(self._pool)

    async def check(self, model_matches: int) -> None:
        """Raise LedgerUnavailable unless model calls can be booked here.

        `model_matches` is how many finished matches with model seats the match
        database holds. Each of them booked calls, so an empty ledger beside
        them is not the one they were booked in (a wrong URL, a lost volume),
        and its month sum would let the month cap be passed.
        """
        await self.prepare()
        async with _reading():
            booked = await self._pool.fetchval("SELECT EXISTS (SELECT 1 FROM model_calls)")
        if not booked and model_matches:
            raise LedgerUnavailable(
                f"The spend ledger has no calls, but {model_matches} finished matches with "
                "models are stored: it is not the ledger they were booked in. "
                "Check LEDGER_DATABASE_URL."
            )

    async def book(
        self,
        match_id: UUID,
        player: PlayerId,
        model: str,
        cost: int,
        *,
        match_cap: int,
        month_cap: int,
        now: datetime,
    ) -> int:
        """Book a call that costs at most `cost` and return its id.

        Raises MatchPaused, and books nothing, if the call could take the match
        or the calendar month of `now` (UTC) past its cap. Check and booking are
        one step, so calls that start at the same moment cannot pass together.
        """
        month = now.astimezone(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        async with self._pool.acquire() as connection, connection.transaction():
            await connection.execute("SELECT pg_advisory_xact_lock($1)", _LEDGER_LOCK)
            spent = await connection.fetchrow(
                "SELECT coalesce(sum(cost_micro_eur) FILTER (WHERE match_id = $1), 0)::bigint"
                " AS match_cap,"
                " coalesce(sum(cost_micro_eur) FILTER (WHERE called_at >= $2), 0)::bigint"
                " AS month_cap "
                "FROM model_calls WHERE match_id = $1 OR called_at >= $2",
                match_id,
                month,
            )
            for reason, cap in (("match_cap", match_cap), ("month_cap", month_cap)):
                if spent[reason] + cost > cap:
                    raise MatchPaused(
                        reason,
                        player=player,
                        spent_micro_eur=spent[reason],
                        cap_micro_eur=cap,
                        call_micro_eur=cost,
                    )
            return await connection.fetchval(
                "INSERT INTO model_calls (match_id, player, model, called_at, cost_micro_eur) "
                "VALUES ($1, $2, $3, $4, $5) RETURNING id",
                match_id,
                player,
                model,
                now,
                cost,
            )

    async def month_spent(self, now: datetime) -> int:
        """What every call of the calendar month of `now` (UTC) cost, in millionths of a euro.

        Raises LedgerUnavailable when the ledger cannot be read: never a 0 that is not true.
        """
        month = now.astimezone(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        async with _reading():
            return await self._pool.fetchval(
                "SELECT coalesce(sum(cost_micro_eur), 0)::bigint FROM model_calls "
                "WHERE called_at >= $1",
                month,
            )

    async def output_tokens(self, model_ids: Sequence[str]) -> dict[str, tuple[int, float]]:
        """For each of these models with reported answers: (answers, output tokens per answer)."""
        async with _reading():
            rows = await self._pool.fetch(
                "SELECT model, count(*) AS answers, avg(output_tokens) AS mean FROM model_calls "
                "WHERE model = ANY($1::text[]) AND output_tokens IS NOT NULL GROUP BY model",
                list(model_ids),
            )
        return {row["model"]: (int(row["answers"]), float(row["mean"])) for row in rows}

    async def match_costs(self, match_id: UUID) -> dict[PlayerId, int]:
        """What each player of a match has cost so far, in millionths of a euro."""
        async with _reading():
            rows = await self._pool.fetch(
                "SELECT player, sum(cost_micro_eur) AS cost FROM model_calls "
                "WHERE match_id = $1 GROUP BY player ORDER BY player",
                match_id,
            )
        return {row["player"]: int(row["cost"]) for row in rows}

    async def costs(self, match_ids: Sequence[UUID]) -> dict[UUID, int]:
        """What each of these matches has cost, in millionths of a euro; 0 without calls."""
        async with _reading():
            rows = await self._pool.fetch(
                "SELECT match_id, sum(cost_micro_eur) AS cost FROM model_calls "
                "WHERE match_id = ANY($1::uuid[]) GROUP BY match_id",
                list(match_ids),
            )
        spent = {row["match_id"]: int(row["cost"]) for row in rows}
        return {match_id: spent.get(match_id, 0) for match_id in match_ids}

    async def seat_costs(self, match_ids: Sequence[UUID]) -> dict[tuple[UUID, PlayerId], int]:
        """What each seat of these matches has cost, keyed by (match, player); seats without
        calls are left out."""
        async with _reading():
            rows = await self._pool.fetch(
                "SELECT match_id, player, sum(cost_micro_eur) AS cost FROM model_calls "
                "WHERE match_id = ANY($1::uuid[]) GROUP BY match_id, player",
                list(match_ids),
            )
        return {(row["match_id"], row["player"]): int(row["cost"]) for row in rows}

    async def settle(self, call_id: int, input_tokens: int, output_tokens: int, cost: int) -> None:
        """Replace the upper bound of a booked call by what it was billed for."""
        await self._pool.execute(
            "UPDATE model_calls SET input_tokens = $2, output_tokens = $3, cost_micro_eur = $4 "
            "WHERE id = $1",
            call_id,
            input_tokens,
            output_tokens,
            cost,
        )
