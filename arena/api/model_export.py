"""One model's matches as a CSV for analysis: GET /models/{id}/export.

One row per seat the model played in a finished, failed, interrupted or aborted match (a match
that is still running has no result yet). Only public facts and counts: no seed, no log, no
hidden cards. `docs/METRICS.md` ("Model export") defines the columns.
"""

import csv
import io
import re
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

from arena.config import load_config
from arena.db.ledger import LedgerUnavailable
from arena.ratings.store import unrated_reason

router = APIRouter(tags=["models"])

COLUMNS = [
    "match_id",
    "game",
    "status",
    "origin",
    "started_at",
    "finished_at",
    "seat",
    "personality",
    "players",
    "opponents",
    "rank",
    "won",
    "rated",
    "unrated_reason",
    "rating_before",
    "rating_after",
    "answers_accepted",
    "answers_rejected",
    "fallback_moves",
    "repaired_answers",
    "cost_micro_eur",
    "prompt_version",
    "memory",
    "batch_id",
]


def safe(value: Any) -> Any:
    """A cell a spreadsheet will not run as a formula: text that starts with = + - @ (or a tab or
    return) gets a leading quote. Numbers stay numbers."""
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@", chr(9), chr(13)):
        return "'" + value
    return value


@router.get("/models/{model_id}/export")
async def export_model(model_id: str, request: Request) -> Response:
    """Per-match statistics of one model as CSV, one row per seat it played, oldest first.

    `opponents` are the other seats' model ids (`bot` for a random bot), joined with `;`.
    `rating_before` and `rating_after` are empty for an unrated match; `cost_micro_eur` is empty
    while the ledger cannot be read (unknown, not 0). Known models without matches give the
    header only; an id that is neither configured nor played is 404.
    """
    pool = request.app.state.pool
    matches = await pool.fetch(
        "SELECT m.id, m.game, m.status, m.origin, m.started_at, m.finished_at, m.seats, "
        "m.placements, m.prompt_version, m.memory, m.batch->>'id' AS batch_id, "
        "r.match_id IS NOT NULL AS rated FROM matches m "
        "LEFT JOIN rated_matches r ON r.match_id = m.id "
        "WHERE m.status <> 'running' AND EXISTS "
        "(SELECT 1 FROM jsonb_each(m.seats) s WHERE s.value->>'model_id' = $1) "
        "ORDER BY m.started_at, m.id",
        model_id,
    )
    if not matches and model_id not in load_config().models:
        raise HTTPException(404, f"No model {model_id}")
    ids = [m["id"] for m in matches]
    counts = await pool.fetch(
        "SELECT match_id, data->>'player' AS seat, "
        "count(*) FILTER (WHERE type = 'action_accepted') AS accepted, "
        "count(*) FILTER (WHERE type = 'action_rejected') AS rejected, "
        "count(*) FILTER (WHERE type = 'decision' AND data->>'fallback' IS NOT NULL) AS fallback, "
        "count(*) FILTER (WHERE type = 'decision' AND data->>'fallback' IS NULL "
        "  AND jsonb_typeof(data->'repairs') = 'array' "
        "  AND jsonb_array_length(data->'repairs') > 0) AS repaired "
        "FROM match_events WHERE match_id = ANY($1::uuid[]) "
        "AND type IN ('action_accepted', 'action_rejected', 'decision') "
        "GROUP BY match_id, data->>'player'",
        ids,
    )
    ratings = await pool.fetch(
        "SELECT s.match_id, s.seat, p.rating_before, p.rating_after FROM match_seats s "
        "JOIN match_placements p ON p.match_id = s.match_id AND p.profile_id = s.profile_id "
        "WHERE s.match_id = ANY($1::uuid[])",
        ids,
    )
    try:
        costs: dict[tuple[UUID, str], int] | None = await request.app.state.live.ledger.seat_costs(
            ids
        )
    except LedgerUnavailable:
        costs = None
    by_seat = {(c["match_id"], c["seat"]): c for c in counts}
    rating_of = {(r["match_id"], r["seat"]): r for r in ratings}

    out = io.StringIO()
    writer = csv.DictWriter(out, COLUMNS, lineterminator="\n")
    writer.writeheader()
    for m in matches:
        seats = m["seats"]
        seat_models = {
            seat: info["model_id"]
            for seat, info in seats.items()
            if info.get("kind") == "model" and info.get("model_id")
        }
        rank_of = {p["player"]: p["rank"] for p in (m["placements"] or [])}
        for seat, info in seats.items():
            if info.get("model_id") != model_id:
                continue
            key = (m["id"], seat)
            counted: Any = by_seat.get(key)
            rating: Any = rating_of.get(key)
            rank = rank_of.get(seat)
            row = {
                "match_id": m["id"],
                "game": m["game"],
                "status": m["status"],
                "origin": m["origin"],
                "started_at": m["started_at"].isoformat(),
                "finished_at": m["finished_at"].isoformat() if m["finished_at"] else "",
                "seat": seat,
                "personality": info.get("personality") or "",
                "players": len(seats),
                "opponents": ";".join(
                    sorted(o.get("model_id") or "bot" for s, o in seats.items() if s != seat)
                ),
                "rank": "" if rank is None else rank,
                "won": "" if rank is None else int(rank == 1),
                "rated": int(m["rated"]),
                "unrated_reason": ""
                if m["rated"] or m["status"] != "finished"
                else unrated_reason(seat_models, model_id),
                "rating_before": "" if rating is None else round(rating["rating_before"], 1),
                "rating_after": "" if rating is None else round(rating["rating_after"], 1),
                "answers_accepted": counted["accepted"] if counted else 0,
                "answers_rejected": counted["rejected"] if counted else 0,
                "fallback_moves": counted["fallback"] if counted else 0,
                "repaired_answers": counted["repaired"] if counted else 0,
                "cost_micro_eur": "" if costs is None else costs.get(key, 0),
                "prompt_version": m["prompt_version"] or "",
                "memory": int(m["memory"]),
                "batch_id": m["batch_id"] or "",
            }
            writer.writerow({k: safe(v) for k, v in row.items()})
    plain = re.sub(r"[^A-Za-z0-9._-]", "_", model_id)
    return Response(
        out.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"content-disposition": f'attachment; filename="aigameversus-{plain}.csv"'},
    )
