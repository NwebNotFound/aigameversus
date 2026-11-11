"""FastAPI application of the arena server."""

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from arena.db.database import connect, migrate


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Bring the database schema up to date before the server takes requests."""
    pool = await connect(os.environ["DATABASE_URL"])
    try:
        await migrate(pool)
    finally:
        await pool.close()
    yield


app = FastAPI(title="AIGameVersus Arena", lifespan=lifespan)


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness probe for Docker and CI. Answers only after startup has finished."""
    return {"status": "ok"}
