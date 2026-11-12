"""FastAPI application of the arena server."""

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from arena.api import (
    analytics,
    batches,
    chronicle,
    export,
    matches,
    memory,
    model_export,
    models,
    qualify,
    ratings,
    referee,
    setup,
    transcript,
    viewer_help,
    werewolf,
)
from arena.api.live import LiveMatches
from arena.api.matches import Estimates
from arena.api.qualify import Jobs
from arena.db.database import connect, ledger_url, migrate
from arena.db.ledger import Ledger, LedgerUnavailable
from arena.db.qualification_store import QualificationStore
from arena.games import load_games

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Bring the database schema up to date, then keep the pool open for the requests.

    The spend ledger may live in a database of its own (LEDGER_DATABASE_URL).
    The server starts without it: bot matches play, and model seats and costs
    are refused until it answers.

    Matches run inside this process: what an earlier process left running is
    marked as interrupted, and what runs at shutdown is stopped.
    """
    url = os.environ["DATABASE_URL"]
    pool = await connect(url)
    ledger_pool = pool if ledger_url(url) == url else await connect(ledger_url(url), min_size=0)
    try:
        await migrate(pool)
        ledger = Ledger(ledger_pool)
        if ledger_pool is not pool:
            try:
                await ledger.prepare()
            except LedgerUnavailable as down:
                log.warning("%s Model seats are refused until it answers.", down)
        app.state.pool = pool
        app.state.live = live = LiveMatches(pool, load_games(), ledger)
        app.state.estimates = Estimates()
        app.state.qualifications = jobs = Jobs(QualificationStore(pool))
        await live.matches.interrupt_running()
        await jobs.store.interrupt_running(datetime.now(UTC))
        try:
            yield
        finally:
            await jobs.stop()
            await live.stop()
    finally:
        if ledger_pool is not pool:
            await ledger_pool.close()
        await pool.close()


app = FastAPI(title="AIGameVersus Arena", lifespan=lifespan)
app.include_router(werewolf.router)
app.include_router(setup.router)
app.include_router(ratings.router)
app.include_router(memory.router)
app.include_router(matches.router)
app.include_router(chronicle.router)
app.include_router(models.router)
app.include_router(model_export.router)
app.include_router(transcript.router)
app.include_router(analytics.router)
app.include_router(export.router)
app.include_router(viewer_help.router)
app.include_router(batches.router)
app.include_router(qualify.router)
app.include_router(referee.router)


@app.exception_handler(LedgerUnavailable)
async def ledger_unavailable(request: Request, down: LedgerUnavailable) -> JSONResponse:
    """No cost is shown and no model is called without the ledger."""
    return JSONResponse({"detail": str(down)}, status_code=503)


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness probe for Docker and CI. Answers only after startup has finished."""
    return {"status": "ok"}
