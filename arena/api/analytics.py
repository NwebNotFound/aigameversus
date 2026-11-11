"""Analytics of a match for the spectator UI: GET /matches/{id}/analytics.

Built from the stored log on every request (`arena.analytics`), so a running match
answers with its turns so far. Without `spoilers` only public events are read.
"""

from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request

from arena.analytics import NoAnalytics, match_analytics
from arena.api.live import LiveMatches
from arena.db.ledger import LedgerUnavailable

router = APIRouter(tags=["analytics"])


@router.get("/matches/{match_id}/analytics")
async def analytics(
    request: Request,
    match_id: UUID,
    spoilers: Annotated[
        bool, Query(description="Include what players hid: their real cards, revolver risk")
    ] = False,
) -> dict[str, Any]:
    """Per move, per player and per round numbers of one match; docs/METRICS.md defines them.

    404 for an unknown match or a game without analytics yet.
    """
    live: LiveMatches = request.app.state.live
    record = await live.matches.get(match_id)
    if record is None:
        raise HTTPException(404, f"No match {match_id}")
    try:
        names = await live.matches.display_names(record)
        result = match_analytics(record.game, await live.log(match_id), spoilers, names)
    except NoAnalytics as missing:
        raise HTTPException(404, str(missing)) from missing
    # Who sat where (seat to model id; null for a bot), so a batch groups like with like.
    seats = record.seats or {}
    result["meta"]["seats"] = {
        seat: seats[seat].model_id if seat in seats else None for seat in record.players
    }
    if "report" in result:
        glance = result["report"]["at_a_glance"]
        end = record.finished_at or datetime.now(UTC)
        glance["duration_s"] = round((end - record.started_at).total_seconds())
        try:
            costs = await live.ledger.match_costs(match_id)
            glance["cost_micro_eur"] = sum(costs.values())
            for row in result["report"]["ranking"]:
                row["cost_micro_eur"] = costs.get(row["player"], 0)
        except LedgerUnavailable:  # the report stays readable; the cost is unknown, not 0
            glance["cost_micro_eur"] = None
            for row in result["report"]["ranking"]:
                row["cost_micro_eur"] = None
        result["report"]["columns"].append(
            {"key": "cost_micro_eur", "label": {"en": "Cost", "de": "Kosten"}, "kind": "micro_eur"}
        )
    return result
