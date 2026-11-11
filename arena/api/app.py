"""FastAPI application of the arena server."""

from fastapi import FastAPI

app = FastAPI(title="AIGameVersus Arena")


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness probe for Docker and CI."""
    return {"status": "ok"}
