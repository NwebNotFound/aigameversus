"""FastAPI application of the arena server."""

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from arena.api import chronicle, matches, memory, ratings, setup, transcript, werewolf
from arena.api.live import LiveMatches
from arena.db.database import connect, migrate
from arena.games import load_games


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Bring the database schema up to date, then keep the pool open for the requests.

    Matches run inside this process: what an earlier process left running is
    marked as interrupted, and what runs at shutdown is stopped.
    """
    pool = await connect(os.environ["DATABASE_URL"])
    try:
        await migrate(pool)
        app.state.pool = pool
        app.state.live = live = LiveMatches(pool, load_games())
        await live.matches.interrupt_running()
        try:
            yield
        finally:
            await live.stop()
    finally:
        await pool.close()


app = FastAPI(title="AIGameVersus Arena", lifespan=lifespan)
app.include_router(werewolf.router)
app.include_router(setup.router)
app.include_router(ratings.router)
app.include_router(memory.router)
app.include_router(matches.router)
app.include_router(chronicle.router)
app.include_router(transcript.router)


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness probe for Docker and CI. Answers only after startup has finished."""
    return {"status": "ok"}
