"""How reliably a model has played here: from the arena's own logs, never from a provider.

A verdict rests on a model's newest moves (the `decision` events of its seats)
and its newest matches. It says what happened on this arena, with its routes
and settings; it is not a judgement of the model in general. The thresholds
are `reliability` in config/models.yaml.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal

import asyncpg

from arena.config import ReliabilityRules

_RECENT_MATCHES = 10  # matches read per model, newest first

Status = Literal["ok", "unreliable", "unknown"]


@dataclass(frozen=True)
class Reliability:
    status: Status
    reason: str | None  # why unreliable or unknown; None when ok
    n: int  # the moves the verdict rests on
    matches: int  # the distinct matches those moves come from
    fallback_share: float | None
    agent_failed_recent: int  # of the newest `matches` rule's matches, those a seat gave up in
    telemetry_moves: int  # of the n moves, those that report cutoffs and rate limits
    cutoff_share: float | None  # of those, the share with an answer cut off; None without any
    rate_limits_per_move: float | None  # of those, rate-limited calls per move
    rejected_rate: float | None  # refused answers over all answers of the n moves
    answers: int  # all answers of the n moves, corrections included: rejected_rate's base
    rejected_cut_off: int  # of the refused answers, those cut off at the output limit
    last_seen: str | None  # when its newest move was logged (ISO), None if never
    warnings: list[str] = field(default_factory=list)  # what costs time without being a failure


def verdict(
    moves: Sequence[tuple[str, dict]],
    failed_recently: int,
    rules: ReliabilityRules,
    last_seen: str | None = None,
) -> Reliability:
    """The verdict from a model's newest moves, newest first, each with its match id."""
    moves = list(moves)[: rules.moves]
    n = len(moves)
    matches = len({match for match, _ in moves})
    share = sum(1 for _, move in moves if move.get("fallback")) / n if n else None
    # Logs before the counters existed say nothing about cut-offs: they are not zeros.
    told = [move for _, move in moves if "cutoffs" in move and "rate_limits" in move]
    cut = sum(1 for m in told if m["cutoffs"]) / len(told) if told else None
    limited = sum(m["rate_limits"] for m in told) / len(told) if told else None
    answers = sum(move.get("answers") or 0 for _, move in moves)
    # Every answer of a move but the accepted one was refused (all of them, on a fallback).
    refused = [
        max((move.get("answers") or 0) - (0 if move.get("fallback") else 1), 0) for _, move in moves
    ]
    rejected_rate = sum(refused) / answers if answers else None
    rejected_cut = sum(
        min(move.get("cutoffs") or 0, count)
        for (_, move), count in zip(moves, refused, strict=True)
    )
    warnings = []
    if cut is not None and cut > rules.cut_off_above:
        warnings.append(
            f"cut off often: {rejected_cut} of {sum(refused)} refused answers ran into the output"
            " limit (raise the limit; not missing tools)"
        )
    if limited is not None and limited > rules.throttled_above:
        warnings.append("often rate-limited by the provider route")
    if n and len(told) < n:
        warnings.append(f"cut-offs and rate limits known for {len(told)} of {n} moves only")

    def said(status: Status, reason: str | None, failed: int = 0) -> Reliability:
        return Reliability(
            status,
            reason,
            n,
            matches,
            share,
            failed,
            len(told),
            cut,
            limited,
            rejected_rate,
            answers,
            rejected_cut,
            last_seen,
            warnings,
        )

    if failed_recently:
        last = rules.matches
        return said(
            "unreliable",
            f"its seat gave up in {failed_recently} of its last {last} matches",
            failed_recently,
        )
    if n < rules.moves:
        return said("unknown", f"only {n} moves played here, fewer than {rules.moves}")
    if share is not None and share > rules.fallback_above:
        return said(
            "unreliable", f"the random bot played {round(share * 100)} % of its last {n} moves"
        )
    return said("ok", None)


async def reliabilities(
    pool: asyncpg.Pool, model_ids: Sequence[str], rules: ReliabilityRules
) -> dict[str, Reliability]:
    """The verdict of every one of these models; a model never seated here is unknown.

    Matches are ranked per model by their start, so a model in two seats of one
    match counts that match once.
    """
    rows = await pool.fetch(
        "WITH seated AS ("
        "  SELECT m.id AS match_id, m.started_at, s.key AS seat, s.value->>'model_id' AS model,"
        "    dense_rank() OVER (PARTITION BY s.value->>'model_id' ORDER BY m.started_at DESC,"
        "      m.id DESC) AS recent"
        "  FROM matches m, jsonb_each(m.seats) s"
        "  WHERE s.value->>'kind' = 'model' AND s.value->>'model_id' = ANY($1::text[])) "
        "SELECT sd.model, sd.match_id, sd.recent, e.type, e.data, e.recorded_at FROM seated sd "
        "JOIN match_events e ON e.match_id = sd.match_id AND e.data->>'player' = sd.seat "
        "  AND e.type IN ('decision', 'agent_failed') "
        "WHERE sd.recent <= $2 "
        "ORDER BY sd.model, sd.recent, e.seq DESC",
        list(model_ids),
        max(_RECENT_MATCHES, rules.matches),
    )
    moves: dict[str, list[tuple[str, dict]]] = {}
    failed: dict[str, set[int]] = {}
    seen: dict[str, str] = {}
    for row in rows:
        stamp = row["recorded_at"].isoformat()
        seen[row["model"]] = max(seen.get(row["model"], stamp), stamp)
        if row["type"] == "decision":
            moves.setdefault(row["model"], []).append((str(row["match_id"]), row["data"]))
        elif row["recent"] <= rules.matches:
            failed.setdefault(row["model"], set()).add(row["recent"])
    return {
        model: verdict(moves.get(model, []), len(failed.get(model, ())), rules, seen.get(model))
        for model in model_ids
    }
