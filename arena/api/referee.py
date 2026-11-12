"""Jev step 3: POST /matches/{id}/referee runs the post-match referee; GET reads its tags.

Running it spends money (one Jev call) and has the gates of Jev: ARENA_ALLOW_JEV=1 (403;
off until Nils approves real Jev calls), confirm_spend (422) and a durable ledger (503).
Only a finished match with model seats is judged, once (409 for a second run; a run is
claimed before Jev is called, so two requests at once pay once). A failure that cost
nothing (Jev off, rate limited, a cap) may be run again. The call is
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
from arena.engine.types import MatchPaused, match_budget_of
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


# Failures that cost nothing (nothing was sent, or it was refused before anything was
# generated) may be run again; every other result is final: one paid run per match.
UNPAID = ("disabled", "rate_limited")
STALE_MINUTES = 10  # a `running` row this old was left by a request that died


async def _claim(pool, match_id: UUID, picked, questions) -> bool:
    """Take the match's one run: a new row, or a failure that cost nothing, or a stale run."""
    claimed = await pool.fetchval(
        "INSERT INTO referee_runs (match_id, created_at, status, reason, rubric, selection,"
        " questions, tags) VALUES ($1, $2, 'running', NULL, $3, $4::jsonb, $5::jsonb, '[]')"
        " ON CONFLICT (match_id) DO UPDATE SET created_at = EXCLUDED.created_at,"
        " status = 'running', reason = NULL, rubric = EXCLUDED.rubric,"
        " selection = EXCLUDED.selection, questions = EXCLUDED.questions, tags = '[]'"
        " WHERE (referee_runs.status = 'failed'"
        "   AND (referee_runs.reason = ANY($6::text[]) OR referee_runs.reason LIKE 'cap (%'))"
        " OR (referee_runs.status = 'running'"
        "   AND referee_runs.created_at < $2 - make_interval(mins => $7))"
        " RETURNING match_id",
        match_id,
        datetime.now(UTC),
        RUBRIC_VERSION,
        json.dumps(picked),
        json.dumps(questions),
        list(UNPAID),
        STALE_MINUTES,
    )
    return claimed is not None


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
    # Claimed before anything is paid: of two requests at once, one runs, the other gets 409.
    if not await _claim(pool, match_id, picked, questions):
        raise HTTPException(409, "This match has been judged: one referee run per match.")
    # The match's own spend limit holds for its referee too.
    budget = Budget(live.ledger, match_id, config, match_eur=match_budget_of(record.settings))
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
        "UPDATE referee_runs SET status = $2, reason = $3, tags = $4::jsonb WHERE match_id = $1",
        match_id,
        status,
        reason,
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
