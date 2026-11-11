"""Leaderboard and player profile endpoints."""

from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from arena.db.event_store import EventStore
from arena.ratings.store import RatingStore, Standing
from arena.stats import STATS

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


class ProfileOut(BaseModel):
    id: UUID
    name: str
    model_id: str
    personality_id: str | None
    overall: StandingOut | None = Field(description="null until the first rated match")
    ratings: list[GameStanding]
    recent_matches: list[RecentMatch]


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


# Statistics count the newest matches of a game only, so a page view stays cheap
# also for a random-bot profile, which sits in every bot match.
MAX_STATS_MATCHES = 200


class GameStatsOut(BaseModel):
    game_id: str
    matches: int = Field(
        description="Rated matches of this game counted: the newest, at most MAX_STATS_MATCHES"
    )
    stats: dict[str, Any] | None = Field(
        description="The game's totals (see arena/stats/<game>.py); null without matches"
    )


class ProfileStats(BaseModel):
    profile_id: UUID
    games: list[GameStatsOut]


@router.get("/profiles/{profile_id}/stats")
async def profile_stats(
    profile_id: UUID,
    store: Store,
    request: Request,
    game: Annotated[str | None, Query(description="Only this game")] = None,
) -> ProfileStats:
    """The player's statistics per game, computed from the logs of its rated matches.

    Without `game`, every game with statistics the player has played. Each game
    counts its newest `MAX_STATS_MATCHES` rated matches.
    """
    if game is not None and game not in STATS:
        raise HTTPException(status_code=404, detail=f"no statistics for the game {game!r}")
    if await store.profile(profile_id) is None:
        raise HTTPException(status_code=404, detail="profile not found")
    played = await store.seats(profile_id)
    logs = EventStore(request.app.state.pool)
    games = []
    for game_id in [game] if game else sorted(g for g in played if g in STATS):
        per_match = []
        for match_id, seat in played.get(game_id, [])[-MAX_STATS_MATCHES:]:
            seat_stats = STATS[game_id].match_stats(await logs.load(match_id)).get(seat)
            if seat_stats is not None:
                per_match.append(seat_stats)
        totals = STATS[game_id].aggregate(per_match).model_dump() if per_match else None
        games.append(GameStatsOut(game_id=game_id, matches=len(per_match), stats=totals))
    return ProfileStats(profile_id=profile_id, games=games)
