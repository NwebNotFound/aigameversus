"""Analytics of a match for the spectator UI: GET /matches/{id}/analytics.

Built from the stored log on every request (`arena.analytics`), so a running match
answers with its turns so far. Without `spoilers` only public events are read.
"""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request

from arena.analytics import NoAnalytics, match_analytics
from arena.api.live import LiveMatches

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
        result = match_analytics(record.game, await live.log(match_id), spoilers)
    except NoAnalytics as missing:
        raise HTTPException(404, str(missing)) from missing
    # Who sat where (seat to model id; null for a bot), so a batch groups like with like.
    seats = record.seats or {}
    result["meta"]["seats"] = {
        seat: seats[seat].model_id if seat in seats else None for seat in record.players
    }
    return result
