"""What players remember: trust and notes per pair of profiles, and their past matches."""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from arena.memory.store import MemoryStore
from arena.ratings.store import RatingStore

router = APIRouter(tags=["memory"])


class NoteOut(BaseModel):
    match_id: UUID
    game_id: str
    text: str


class RelationOut(BaseModel):
    profile_id: UUID = Field(description="The other player")
    name: str
    model_id: str
    trust: int = Field(ge=-100, le=100, description="-100 distrust to +100 trust; 0 at the start")
    notes: list[NoteOut] = Field(description="What happened between them, newest first")


class Relations(BaseModel):
    profile_id: UUID
    relations: list[RelationOut]


@router.get("/profiles/{profile_id}/relations")
async def relations(profile_id: UUID, request: Request) -> Relations:
    """What the player thinks of every player it has met: strongest feeling first."""
    pool = request.app.state.pool
    if await RatingStore(pool).profile(profile_id) is None:
        raise HTTPException(status_code=404, detail="profile not found")
    found = await MemoryStore(pool).relationships(profile_id)
    return Relations(
        profile_id=profile_id,
        relations=[
            RelationOut(
                profile_id=r.other_id,
                name=r.name,
                model_id=r.model_id,
                trust=r.trust,
                notes=[
                    NoteOut(match_id=n.match_id, game_id=n.game_id, text=n.text) for n in r.notes
                ],
            )
            for r in found
        ],
    )


class MemoryOut(BaseModel):
    match_id: UUID
    game_id: str
    summary: str = Field(description="The match from this player's view")
    created_at: datetime


@router.get("/profiles/{profile_id}/memories")
async def memories(profile_id: UUID, request: Request) -> list[MemoryOut]:
    """The player's summaries of its 20 newest remembered matches, newest first."""
    pool = request.app.state.pool
    if await RatingStore(pool).profile(profile_id) is None:
        raise HTTPException(status_code=404, detail="profile not found")
    return [
        MemoryOut(
            match_id=m.match_id, game_id=m.game_id, summary=m.summary, created_at=m.created_at
        )
        for m in await MemoryStore(pool).memories(profile_id)
    ]


class ResetRequest(BaseModel):
    profile_id: UUID | None = Field(
        None, description="Only what this player remembers; null: every player's memory"
    )
    confirm: bool = Field(
        False, description="Must be true to forget every player's memory (no profile_id)"
    )


class ResetOut(BaseModel):
    relationships: int = Field(description="Relationships forgotten")
    memories: int = Field(description="Match summaries forgotten")


@router.post("/memory/reset")
async def reset_memory(request: Request, reset: ResetRequest) -> ResetOut:
    """Forget relationships and match summaries, for a new season or a fair benchmark.

    Ratings and statistics stay. A match that was already remembered is not
    remembered again.
    """
    if reset.profile_id is None and not reset.confirm:
        raise HTTPException(
            status_code=422,
            detail='Forgetting the memory of every player needs "confirm": true; '
            "it cannot be undone.",
        )
    done = await MemoryStore(request.app.state.pool).reset(reset.profile_id)
    return ResetOut(relationships=done.relationships, memories=done.memories)
