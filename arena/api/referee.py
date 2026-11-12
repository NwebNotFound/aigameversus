"""Jev step 3: POST /matches/{id}/referee runs the post-match referee; GET reads its tags.

Running it spends money (one Jev call) and has the gates of Jev: ARENA_ALLOW_JEV=1 (403;
off until Nils approves real Jev calls), confirm_spend (422) and a durable ledger (503).
Only a finished match with model seats is judged, once (409 for a second run). The call is
booked in the ledger under the match id, inside its cap and the month cap. The tags are
spoiler-rich research data: GET answers them with `spoilers=true` only.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from arena.agents.budget import Budget
from arena.analytics.talk import talk_checks
from arena.api.matches import Live, _seat_config
from arena.engine.types import MatchPaused
from arena.jev.client import ALLOW_JEV, HttpJev, JevClient, JevError
from arena.jev.config import load_jev_config
from arena.jev.referee import RUBRIC_VERSION, check_scores, moments, request_of, tags_of

router = APIRouter(tags=["referee"])


class RefereeRequest(BaseModel):
    confirm_spend: bool = Field(False, description="One Jev call is paid: true to run it")


class RefereeRun(BaseModel):
    match_id: UUID
    created_at: datetime
    status: str = Field(description="done, or failed with a reason")
    reason: str | None
    rubric: str
    selection: dict[str, Any] = Field(description="The chosen moments and counts per category")
    questions: dict[str, Any]
    tags: list[dict[str, Any]] = Field(description="Per moment, unvalidated research tags")


def jev_client() -> JevClient:
    """The real client; it sends nothing without ARENA_ALLOW_JEV=1. Tests use a FakeJev."""
    jev = load_jev_config()
    return HttpJev(jev.model, jev.endpoint, jev.timeout_seconds)


async def _stored(pool, match_id: UUID) -> RefereeRun | None:
    row = await pool.fetchrow(
        "SELECT match_id, created_at, status, reason, rubric, selection, questions, tags"
        " FROM referee_runs WHERE match_id = $1",
        match_id,
    )
    if row is None:
        return None
    data = dict(row)
    for key in ("selection", "questions", "tags"):
        if isinstance(data[key], str):
            data[key] = json.loads(data[key])
    return RefereeRun(**data)


@router.post("/matches/{match_id}/referee", status_code=201)
async def run_referee(
    match_id: UUID, body: RefereeRequest, request: Request, live: Live
) -> RefereeRun:
    """Judge 5 moments of a finished model match with one Jev call; research tags only."""
    if os.environ.get(ALLOW_JEV) != "1":
        raise HTTPException(
            403, f"The referee calls Jev, which is off on this server ({ALLOW_JEV}=1 allows it)."
        )
    if not body.confirm_spend:
        raise HTTPException(422, "The referee makes one paid Jev call: send confirm_spend: true.")
    record = await live.matches.get(match_id)
    if record is None:
        raise HTTPException(404, f"No match {match_id}")
    if record.status != "finished":
        raise HTTPException(
            409, "Only a finished match is judged: the referee never touches a live one."
        )
    pool = request.app.state.pool
    if await _stored(pool, match_id) is not None:
        raise HTTPException(409, "This match has been judged: one referee run per match.")
    models = {seat for seat, s in (record.seats or {}).items() if s.kind == "model"}
    if not models:
        raise HTTPException(422, "A match of bots has no reasoning to judge.")
    events = await live.log(match_id)
    picked = moments(events, models)
    if not picked["moments"]:
        raise HTTPException(422, "This match has no model moves to judge.")
    names = await live.matches.display_names(record)
    checked = {
        (tag["seq"], tag["player"])
        for tag in talk_checks(record.game, list(enumerate(events)), True, names).get("tags", [])
    }
    state, questions = request_of(record.game, events, picked, checked)
    await live.ledger.check(await live.matches.model_matches())  # 503 when not durable
    config = await _seat_config([s.model_id for s in record.seats.values() if s.model_id])
    budget = Budget(live.ledger, match_id, config)
    jev = load_jev_config()
    status, reason, tags = "done", None, []
    try:
        result = await budget.jev(jev_client(), jev, "referee")(state, questions)
        check_scores(result, questions)
        tags = tags_of(result, picked)
    except JevError as error:
        status, reason = "failed", error.reason
    except MatchPaused as pause:
        status, reason = "failed", f"cap ({pause.reason})"
    await pool.execute(
        "INSERT INTO referee_runs (match_id, created_at, status, reason, rubric, selection,"
        " questions, tags) VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7::jsonb, $8::jsonb)",
        match_id,
        datetime.now(UTC),
        status,
        reason,
        RUBRIC_VERSION,
        json.dumps(picked),
        json.dumps(questions),
        json.dumps(tags),
    )
    run = await _stored(pool, match_id)
    assert run is not None
    return run


@router.get("/matches/{match_id}/referee")
async def get_referee(
    match_id: UUID,
    request: Request,
    spoilers: Annotated[
        bool, Query(description="The tags judge hidden play: spoilers only")
    ] = False,
) -> RefereeRun:
    """The referee's research tags of a match. 403 without spoilers, 404 if never judged."""
    if not spoilers:
        raise HTTPException(403, "The referee's tags judge hidden play: ask with spoilers=true.")
    run = await _stored(request.app.state.pool, match_id)
    if run is None:
        raise HTTPException(404, "This match has not been judged by the referee.")
    return run
