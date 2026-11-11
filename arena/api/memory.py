"""What players remember of each other: trust and notes per pair of profiles."""

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
