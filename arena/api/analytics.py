"""Analytics of a match for the spectator UI: GET /matches/{id}/analytics.

Built from the stored log on every request (`arena.analytics`), so a running match
answers with its turns so far. Without `spoilers` only public events are read.
"""

from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request

from arena.analytics import NoAnalytics, UnknownVersion, match_analytics
from arena.analytics.talk import talk_checks
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
    analytics_version: Annotated[
        str | None,
        Query(description="Throne of Tokens only: civ/1 (default) or civ/2, which adds to it"),
    ] = None,
) -> dict[str, Any]:
    """Per move, per player and per round numbers of one match; docs/METRICS.md defines them.

    404 for an unknown match or a game without analytics yet; 422 for a version the game lacks.
    """
    live: LiveMatches = request.app.state.live
    record = await live.matches.get(match_id)
    if record is None:
        raise HTTPException(404, f"No match {match_id}")
    try:
        names = await live.matches.display_names(record)
        result = match_analytics(
            record.game, await live.log(match_id), spoilers, names, analytics_version
        )
    except NoAnalytics as missing:
        raise HTTPException(404, str(missing)) from missing
    except UnknownVersion as unknown:
        raise HTTPException(422, str(unknown)) from unknown
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
            by_seat = {seat: costs.get(seat, 0) for seat in record.players}
        except LedgerUnavailable:  # the report stays readable; the cost is unknown, not 0
            by_seat = None
        glance["cost_micro_eur"] = None if by_seat is None else sum(by_seat.values())
        glance["cost_by_seat"] = by_seat
        column = {
            "key": "cost_micro_eur",
            "label": {"en": "Cost", "de": "Kosten"},
            "kind": "micro_eur",
            "better": "lower",
        }
        result["report"]["columns"].append(column)
        for row in result["report"]["ranking"]:
            value = None if by_seat is None else by_seat[row["seat"]]
            row["values"].append({**column, "value": value})
    return result


@router.get("/matches/{match_id}/talk-checks")
async def talk_check(
    request: Request,
    match_id: UUID,
    spoilers: Annotated[
        bool, Query(description="Include checks that need the players' hidden cards")
    ] = False,
) -> dict[str, Any]:
    """What players said about their cards or role, against what the engine knows.

    Each tag has the quote, the claim as read, `true` or `false`, and the evidence. The words
    are read with patterns, so a tag is research data (`heuristic`), never a verdict. Without
    `spoilers` Liar's Deck and Poker give no tags, and Werewolf only claims a death disproved.
    """
    live: LiveMatches = request.app.state.live
    record = await live.matches.get(match_id)
    if record is None:
        raise HTTPException(404, f"No match {match_id}")
    names = await live.matches.display_names(record)
    log = list(enumerate(await live.log(match_id)))  # (seq, event), as the analyzers read it
    result = talk_checks(record.game, log, spoilers, names)
    if not result["available"] and "no talk check" in result.get("reason", ""):
        raise HTTPException(404, f"No talk check for {record.game} yet")
    return result
