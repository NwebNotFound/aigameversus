"""FastAPI application of the arena server."""

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from arena.api import ratings, werewolf
from arena.db.database import connect, migrate


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Bring the database schema up to date, then keep the pool open for the requests."""
    pool = await connect(os.environ["DATABASE_URL"])
    try:
        await migrate(pool)
        app.state.pool = pool
        yield
    finally:
        await pool.close()


app = FastAPI(title="AIGameVersus Arena", lifespan=lifespan)
app.include_router(werewolf.router)
app.include_router(ratings.router)


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness probe for Docker and CI. Answers only after startup has finished."""
    return {"status": "ok"}
