"""A batch of matches at a glance: GET /batches/{id}, for lists that show a league as one row."""

from collections import Counter
from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from arena.api.matches import Live
from arena.db.ledger import LedgerUnavailable
from arena.db.match_store import Status

router = APIRouter(tags=["batches"])


class BatchSummary(BaseModel):
    id: str
    label: str = Field(description="The label of the batch's newest match")
    of: int | None = Field(description="How many matches the batch plans; null if not said")
    budget_eur: float | None = Field(description="What the batch may spend; null if not said")
    matches: int = Field(description="Matches started in the batch, replays of a failed one too")
    statuses: dict[Status, int] = Field(description="How many matches have each status")
    cost_micro_eur: int | None = Field(
        description="What the batch's model calls cost so far; null while the ledger cannot be read"
    )
    first_started_at: datetime
    last_started_at: datetime


@router.get("/batches/{batch_id}")
async def batch(batch_id: str, live: Live) -> BatchSummary:
    """How far a batch is and what it cost. 404 when no match carries this batch id."""
    records = await live.matches.recent(batch=batch_id)
    if not records:
        raise HTTPException(404, f"No match is in batch {batch_id!r}")
    newest = records[0].batch
    try:
        costs = await live.ledger.costs([record.id for record in records])
        cost = sum(costs.values())
    except LedgerUnavailable:  # the summary stays readable; the cost is unknown, not 0
        cost = None
    return BatchSummary(
        id=batch_id,
        label=newest.label,
        of=newest.of,
        budget_eur=newest.budget_eur,
        matches=len(records),
        statuses=dict(Counter(record.status for record in records)),
        cost_micro_eur=cost,
        first_started_at=min(record.started_at for record in records),
        last_started_at=max(record.started_at for record in records),
    )
