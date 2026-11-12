"""One match as a file for analysis: GET /matches/{id}/export.

The record, the cost, the log and the analytics (and table-talk checks) in one JSON document,
for a notebook. Without `spoilers` it holds only what a spoiler-free viewer may read: public
events, no seed, public settings. With `spoilers` it is the whole match, hidden cards, roles and
thoughts included. The document says which one it is (`spoilers`).
"""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from arena.analytics import public_log
from arena.api.analytics import analytics, talk_check
from arena.api.live import LiveMatches
from arena.db.ledger import LedgerUnavailable
from arena.transcript.common import public_settings

router = APIRouter(tags=["export"])

FORMAT = "aigameversus-match-export/1"


async def _part(call: Any) -> dict[str, Any] | None:
    """An optional part: null when the game has none yet (the analytics API answers 404)."""
    try:
        return await call
    except HTTPException as missing:
        if missing.status_code == 404:
            return None
        raise


@router.get("/matches/{match_id}/export")
async def export_match(
    request: Request,
    match_id: UUID,
    spoilers: Annotated[
        bool,
        Query(
            description="The whole match: hidden cards, roles, thoughts, the seed. Off: public only"
        ),
    ] = False,
) -> JSONResponse:
    """The record, cost, event log, analytics and talk checks of one match, as a download.

    `events` keep their `seq` (position in the whole log), so a gap shows what was left out.
    `analytics` and `talk_checks` are null for a game without them. 404 for an unknown match.
    """
    live: LiveMatches = request.app.state.live
    record = await live.matches.get(match_id)
    if record is None:
        raise HTTPException(404, f"No match {match_id}")
    log = list(enumerate(await live.log(match_id)))
    shown = log if spoilers else public_log(log)
    match = record.model_dump(mode="json")
    if not spoilers:
        match["seed"] = None
        match["settings"] = public_settings(record.settings)
    try:
        costs = await live.ledger.match_costs(match_id)
        cost: dict[str, Any] | None = {
            "total_micro_eur": sum(costs.values()),
            "players": costs,
        }
    except LedgerUnavailable:
        cost = None  # unknown, not zero
    document = {
        "format": FORMAT,
        "spoilers": spoilers,
        "match": match,
        "cost": cost,
        "events": [{"seq": seq, **event.model_dump(mode="json")} for seq, event in shown],
        "analytics": await _part(analytics(request, match_id, spoilers)),
        "talk_checks": await _part(talk_check(request, match_id, spoilers)),
    }
    name = f"aigameversus-{record.game}-{match_id}{'-full' if spoilers else ''}.json"
    return JSONResponse(document, headers={"content-disposition": f'attachment; filename="{name}"'})
