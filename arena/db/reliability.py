"""How reliably a model has played here: from the arena's own logs, never from a provider.

A verdict rests on a model's newest moves (the `decision` events of its seats)
and its newest matches. It says what happened on this arena, with its routes
and settings; it is not a judgement of the model in general.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal

import asyncpg

MOVES = 20  # the newest moves a verdict rests on
MATCHES = 2  # a seat that gave up in one of the newest this many matches is unreliable
FALLBACK_ABOVE = 0.5  # share of the newest moves the random bot played instead
CUT_OFF_ABOVE = 0.10  # share of the newest moves with an answer cut off at the output limit
THROTTLED_ABOVE = 0.20  # rate-limited calls per move
_RECENT_MATCHES = 10  # matches read per model, newest first

Status = Literal["ok", "unreliable", "unknown"]


@dataclass(frozen=True)
class Reliability:
    status: Status
    reason: str | None  # why unreliable or unknown; None when ok
    n: int  # the moves the verdict rests on
    fallback_share: float | None
    agent_failed_recent: int  # of the newest MATCHES matches, those in which a seat gave up
    warnings: list[str] = field(default_factory=list)  # what is not a failure but costs time


def verdict(moves: Sequence[dict], failed_recently: int) -> Reliability:
    """The verdict from a model's newest moves (decision data, newest first)."""
    moves = list(moves)[:MOVES]
    n = len(moves)
    share = sum(1 for move in moves if move.get("fallback")) / n if n else None
    warnings = []
    if n:
        if sum(1 for m in moves if m.get("cutoffs")) / n > CUT_OFF_ABOVE:
            warnings.append("answers often cut off at the output limit (a setting, not tools)")
        if sum(m.get("rate_limits") or 0 for m in moves) / n > THROTTLED_ABOVE:
            warnings.append("often rate-limited by the provider route")
    if failed_recently:
        reason = f"its seat gave up in {failed_recently} of its last {MATCHES} matches"
        return Reliability("unreliable", reason, n, share, failed_recently, warnings)
    if n < MOVES:
        reason = f"only {n} moves played here, fewer than {MOVES}"
        return Reliability("unknown", reason, n, share, 0, warnings)
    if share is not None and share > FALLBACK_ABOVE:
        reason = f"the random bot played {round(share * 100)} % of its last {n} moves"
        return Reliability("unreliable", reason, n, share, 0, warnings)
    return Reliability("ok", None, n, share, 0, warnings)


async def reliabilities(pool: asyncpg.Pool, model_ids: Sequence[str]) -> dict[str, Reliability]:
    """The verdict of every one of these models; a model never seated here is unknown."""
    rows = await pool.fetch(
        "WITH seated AS ("
        "  SELECT m.id AS match_id, m.started_at, s.key AS seat, s.value->>'model_id' AS model,"
        "    row_number() OVER (PARTITION BY s.value->>'model_id' ORDER BY m.started_at DESC,"
        "      m.id) AS recent"
        "  FROM matches m, jsonb_each(m.seats) s"
        "  WHERE s.value->>'kind' = 'model' AND s.value->>'model_id' = ANY($1::text[])) "
        "SELECT sd.model, sd.recent, e.type, e.data FROM seated sd "
        "JOIN match_events e ON e.match_id = sd.match_id AND e.data->>'player' = sd.seat "
        "  AND e.type IN ('decision', 'agent_failed') "
        "WHERE sd.recent <= $2 "
        "ORDER BY sd.model, sd.started_at DESC, e.seq DESC",
        list(model_ids),
        _RECENT_MATCHES,
    )
    moves: dict[str, list[dict]] = {}
    failed: dict[str, set[int]] = {}
    for row in rows:
        if row["type"] == "decision":
            moves.setdefault(row["model"], []).append(row["data"])
        elif row["recent"] <= MATCHES:
            failed.setdefault(row["model"], set()).add(row["recent"])
    return {model: verdict(moves.get(model, []), len(failed.get(model, ()))) for model in model_ids}
