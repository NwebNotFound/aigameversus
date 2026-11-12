"""The chronicle of a finished match: GET /matches/{id}/chronicle."""

import json
import os
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import NAMESPACE_URL, UUID, uuid5

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field

from arena.agents.budget import MICRO, Budget, cost_micro_eur
from arena.agents.model import ModelCall
from arena.api.live import LiveMatches
from arena.api.matches import ALLOW_MODEL_SEATS, _seat_config
from arena.chronicle import Chronicle, ChronicleError, chronicle_games, tell, to_markdown
from arena.chronicle.ai import AiChronicle, messages, retell, tool_schema
from arena.config import call_options, load_keys
from arena.db.ledger import LedgerUnavailable
from arena.engine.types import MatchPaused

router = APIRouter(tags=["chronicle"])


@router.get("/matches/{match_id}/chronicle", response_model=None)
async def chronicle(
    request: Request,
    match_id: UUID,
    style: Annotated[
        Literal["epic", "news", "sports", "novel"], Query(description="How the story is told")
    ] = "epic",
    lang: Annotated[Literal["en", "de"], Query(description="Language of the story")] = "en",
    format: Annotated[
        Literal["json", "markdown"], Query(description="Chapters as JSON, or one Markdown text")
    ] = "json",
) -> Chronicle | PlainTextResponse:
    """The story of a finished match, from its stored log. Spectator information: it names
    hidden cards and roles, so a match that is still running answers 409."""
    live: LiveMatches = request.app.state.live
    record = await live.matches.get(match_id)
    if record is None:
        raise HTTPException(404, f"No match {match_id}")
    if record.game not in chronicle_games():
        raise HTTPException(
            404, f"No chronicle for {record.game} (games with one: {', '.join(chronicle_games())})"
        )
    if record.status != "finished":
        raise HTTPException(
            409, f"The match is {record.status}; its chronicle exists once it has finished"
        )
    names = await live.matches.display_names(record)  # the names every page shows
    try:
        cost = sum((await live.ledger.match_costs(match_id)).values())
    except LedgerUnavailable:  # the cost is unknown, not 0: the glance box leaves it out
        cost = None
    try:
        story = tell(
            await live.log(match_id),
            style=style,
            lang=lang,
            names=names,
            cost_micro_eur=cost or None,
        )
    except ChronicleError as error:
        raise HTTPException(409, str(error)) from error
    if format == "markdown":
        return PlainTextResponse(to_markdown(story), media_type="text/markdown; charset=utf-8")
    return story


# --- the AI-written chronicle (D-140) ----------------------------------------------------------

CHRONICLE_CAP_EUR = Decimal("0.03")  # the most one chronicle may cost, retries included
STALE_MINUTES = 10  # a `running` row this old was left by a request that died (D-134)


class NewAiChronicle(BaseModel):
    style: Literal["epic", "news", "sports", "novel"] = "epic"
    lang: Literal["en", "de"] = "en"
    model: str = Field(description="Model id of config/models.yaml or GET /models/catalog")
    confirm_spend: bool = Field(False, description="One paid model call: true to make it")


def chronicle_call(budget: Budget, model_id: str) -> ModelCall:
    """The real, metered call of the model; tests replace it with a metered mock."""
    return budget.model("chronicler", model_id)


async def _ai_row(pool, match_id: UUID, style: str, lang: str, model: str):
    return await pool.fetchrow(
        "SELECT status, reason, body FROM ai_chronicles"
        " WHERE match_id = $1 AND style = $2 AND lang = $3 AND model = $4",
        match_id,
        style,
        lang,
        model,
    )


def _body(row) -> dict:
    body = row["body"]
    return json.loads(body) if isinstance(body, str) else body


@router.post("/matches/{match_id}/chronicle/ai", response_model=AiChronicle)
async def write_ai_chronicle(match_id: UUID, new: NewAiChronicle, request: Request):
    """Have a model retell the chronicle of a finished match, once; then it is served cached.

    Spends money (one call, at most EUR 0.03 for this match, style, language and model, every
    retry included): ARENA_ALLOW_MODEL_SEATS (403), confirm_spend (422), the key (503) and a
    durable ledger (503). Each chapter is checked against the template's facts and keeps the
    template text where the rewrite adds a name, number, card or role.
    """
    live: LiveMatches = request.app.state.live
    pool = request.app.state.pool
    record = await live.matches.get(match_id)
    if record is None:
        raise HTTPException(404, f"No match {match_id}")
    if record.game not in chronicle_games():
        raise HTTPException(404, f"No chronicle for {record.game}")
    if record.status != "finished":
        raise HTTPException(409, f"The match is {record.status}: no chronicle before its end")
    cached = await _ai_row(pool, match_id, new.style, new.lang, new.model)
    if cached is not None and cached["status"] == "done":
        return JSONResponse(_body(cached))  # already paid for: served, not written again
    if os.environ.get(ALLOW_MODEL_SEATS) != "1":
        raise HTTPException(
            403, f"AI chronicles make paid calls: off without {ALLOW_MODEL_SEATS}=1"
        )
    if not new.confirm_spend:
        raise HTTPException(422, "An AI chronicle spends money: send confirm_spend: true.")
    config = await _seat_config([new.model])
    if missing := load_keys(config, [new.model]):
        raise HTTPException(503, f"The server lacks {', '.join(missing)}, the provider's API key")
    await live.ledger.check(await live.matches.model_matches())  # 503 when not durable
    names = await live.matches.display_names(record)
    try:
        story = tell(await live.log(match_id), style=new.style, lang=new.lang, names=names)
    except ChronicleError as error:
        raise HTTPException(409, str(error)) from error
    # The worst case of the one call, as the budget books it: refused above the cap.
    sent = messages(story, new.style, new.lang)
    bound = cost_micro_eur(
        config,
        config.models[new.model],
        len(json.dumps([sent, [tool_schema()]])),
        call_options(config, new.model).max_output_tokens,
    )
    cap = int(CHRONICLE_CAP_EUR * MICRO)
    if bound > cap:
        raise HTTPException(
            422,
            f"This chronicle may cost up to {bound / MICRO:.4f} EUR,"
            f" above its {CHRONICLE_CAP_EUR} EUR cap",
        )
    job_id = uuid5(NAMESPACE_URL, f"chronicle/{match_id}/{new.style}/{new.lang}/{new.model}")
    # A running row is another request's, unless it is stale: the request that wrote it died
    # (restart, cancel). Taking it over is safe: the same job id keeps the same cap.
    claimed = await pool.fetchval(
        "INSERT INTO ai_chronicles (match_id, style, lang, model, job_id, status, created_at)"
        " VALUES ($1, $2, $3, $4, $5, 'running', $6)"
        " ON CONFLICT (match_id, style, lang, model) DO UPDATE SET status = 'running',"
        " reason = NULL, created_at = EXCLUDED.created_at WHERE ai_chronicles.status = 'failed'"
        " OR (ai_chronicles.status = 'running'"
        "   AND ai_chronicles.created_at < $6 - make_interval(mins => $7))"
        " RETURNING job_id",
        match_id,
        new.style,
        new.lang,
        new.model,
        job_id,
        datetime.now(UTC),
        STALE_MINUTES,
    )
    if claimed is None:
        raise HTTPException(409, "This chronicle is being written now")
    # Its own id and cap: every retry of this chronicle books against the same EUR 0.03.
    budget = Budget(live.ledger, job_id, config, match_eur=CHRONICLE_CAP_EUR)
    status, reason, body = "done", None, None
    try:
        written = await retell(
            story, new.style, new.lang, names, chronicle_call(budget, new.model), new.model
        )
        if any(check.ai for check in written.checks):
            body = written.model_dump(mode="json")
        else:  # not one chapter in the model's words: no AI chronicle, and a retry may be made
            first = next((check.reason for check in written.checks), None)
            status, reason = "failed", f"no chapter passed ({first})"
    except MatchPaused as pause:
        status, reason = "failed", f"cap ({pause.reason})"
    except Exception as error:  # noqa: BLE001 - a failed call is recorded, the cap holds
        status, reason = "failed", type(error).__name__
    await pool.execute(
        "UPDATE ai_chronicles SET status = $5, reason = $6, body = $7::jsonb"
        " WHERE match_id = $1 AND style = $2 AND lang = $3 AND model = $4",
        match_id,
        new.style,
        new.lang,
        new.model,
        status,
        reason,
        None if body is None else json.dumps(body),
    )
    if status != "done":
        raise HTTPException(502, f"The AI chronicle failed ({reason}); the template one stays")
    return JSONResponse(body, status_code=201)


@router.get("/matches/{match_id}/chronicle/ai", response_model=AiChronicle)
async def read_ai_chronicle(
    match_id: UUID,
    request: Request,
    model: str,
    style: Literal["epic", "news", "sports", "novel"] = "epic",
    lang: Literal["en", "de"] = "en",
):
    """The cached AI-written chronicle, if one was written; 404 otherwise. Spends nothing."""
    row = await _ai_row(request.app.state.pool, match_id, style, lang, model)
    if row is None or row["status"] != "done":
        raise HTTPException(404, "No AI-written chronicle for this match, style, language, model")
    return JSONResponse(_body(row))
