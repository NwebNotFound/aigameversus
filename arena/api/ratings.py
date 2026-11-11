"""Leaderboard and player profile endpoints."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from arena.ratings.store import RatingStore, Standing

router = APIRouter(tags=["ratings"])


def get_store(request: Request) -> RatingStore:
    return RatingStore(request.app.state.pool)


Store = Annotated[RatingStore, Depends(get_store)]


class StandingOut(BaseModel):
    profile_id: UUID
    name: str
    model_id: str
    rating: float = Field(description="Elo rating; 1000 is the start value")
    games_played: int
    win_rate: float | None = Field(description="Share of matches won (rank 1), 0 to 1")
    average_placement: float | None = Field(description="Mean finishing rank, 1 = winner")

    @classmethod
    def of(cls, standing: Standing) -> "StandingOut":
        return cls(
            profile_id=standing.profile_id,
            name=standing.name,
            model_id=standing.model_id,
            rating=round(standing.rating, 1),
            games_played=standing.games_played,
            win_rate=standing.win_rate,
            average_placement=standing.average_placement,
        )


class LeaderboardRow(StandingOut):
    rank: int = Field(description="Position on the board, 1 = highest rating")


class Leaderboard(BaseModel):
    game: str | None = Field(description="The game shown, or null for the overall rating")
    games: list[str] = Field(description="Every game with at least one rated match")
    rows: list[LeaderboardRow]


class GameStanding(StandingOut):
    game_id: str


class RecentMatch(BaseModel):
    match_id: UUID
    game_id: str
    rated_at: datetime
    rank: int
    players: int
    rating_change: float


class NotAvailable(BaseModel):
    available: Literal[False] = False
    note: str = "not available yet"


class ProfileOut(BaseModel):
    id: UUID
    name: str
    model_id: str
    personality_id: str | None
    overall: StandingOut | None = Field(description="null until the first rated match")
    ratings: list[GameStanding]
    recent_matches: list[RecentMatch]
    relations: NotAvailable = Field(default_factory=NotAvailable)
    memory: NotAvailable = Field(default_factory=NotAvailable)


@router.get("/leaderboard")
async def leaderboard(
    store: Store,
    game: Annotated[str | None, Query(description="A game id; omit for the overall rating")] = None,
) -> Leaderboard:
    """Players by rating, best first: in one game, or overall across all games."""
    standings = await store.leaderboard(game)
    return Leaderboard(
        game=game,
        games=await store.rated_games(),
        rows=[
            LeaderboardRow(rank=position, **StandingOut.of(s).model_dump())
            for position, s in enumerate(standings, start=1)
        ],
    )


@router.get("/profiles/{profile_id}")
async def profile(profile_id: UUID, store: Store) -> ProfileOut:
    """One player: rating per game, overall statistics and the latest rated matches."""
    found = await store.profile(profile_id)
    if found is None:
        raise HTTPException(status_code=404, detail="profile not found")
    return ProfileOut(
        id=found.profile_id,
        name=found.name,
        model_id=found.model_id,
        personality_id=found.personality_id,
        overall=StandingOut.of(found.overall) if found.overall else None,
        ratings=[
            GameStanding(game_id=game_id, **StandingOut.of(s).model_dump())
            for game_id, s in found.per_game.items()
        ],
        recent_matches=[
            RecentMatch(
                match_id=m.match_id,
                game_id=m.game_id,
                rated_at=m.rated_at,
                rank=m.rank,
                players=m.players,
                rating_change=round(m.rating_change, 1),
            )
            for m in found.recent_matches
        ],
    )
