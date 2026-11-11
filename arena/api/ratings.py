"""Leaderboard and player profile endpoints."""

from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from arena.api.live import LiveMatches
from arena.config import load_config
from arena.db.event_store import EventStore
from arena.ratings.store import BOT_MODEL_ID, RatingStore, Standing, Usage
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
    kind: Literal["model", "bot"] = Field(description="A real model, or a random bot")
    vendor: str | None = Field(None, description="Who makes the model, from config/models.yaml")
    members: int = Field(1, description="Profiles in this row: more than 1 for grouped bot seats")
    cost_per_game_micro_eur: int | None = Field(
        None,
        description="Average cost of one rated game, in millionths of a euro; null without "
        "cost or while the ledger cannot be read",
    )
    tool_error_rate: float | None = Field(
        None, description="Share of answers the server refused (a wrong tool or an illegal move)"
    )


class Leaderboard(BaseModel):
    game: str | None = Field(description="The game shown, or null for the overall rating")
    games: list[str] = Field(description="Every game with at least one rated match")
    kind: Literal["models", "bots", "all"] = Field(description="Who is shown")
    fallback: bool = Field(
        False, description="True when real models were asked for but none is rated yet: all shown"
    )
    counts: dict[str, int] = Field(description="Rows per kind with the other filters applied")
    show_demo: bool = Field(False, description="Whether the demo profiles are included")
    demo_hidden: int = Field(0, description="Demo profiles left out, when `show_demo` is false")
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


def vendor_of(model_id: str) -> str | None:
    """The maker of a model, from its provider name in config/models.yaml: "z-ai/glm" is z-ai."""
    configured = load_config().models.get(model_id)
    return configured.model.split("/", 1)[0] if configured and "/" in configured.model else None


def is_seat_bot(standing: Standing) -> bool:
    """The per-seat profile of a random bot ("Random Bot p3"), as `bot_profiles` makes them."""
    return standing.model_id == BOT_MODEL_ID and standing.name.startswith("Random Bot ")


def group_seat_bots(standings: list[Standing], usage: dict[UUID, Usage]):
    """One row for all random-bot seats, since a bot has no identity beyond its kind.

    Rating, win rate and placement are averaged over the games each seat played.
    Returns the grouped standing (or None without bots) and the rest.
    """
    bots = [s for s in standings if is_seat_bot(s)]
    rest = [s for s in standings if not is_seat_bot(s)]
    if not bots:
        return None, rest
    games = sum(s.games_played for s in bots)

    def weighted(value) -> float | None:
        pairs = [(value(s), s.games_played) for s in bots if value(s) is not None]
        total = sum(weight for _, weight in pairs)
        return sum(v * w for v, w in pairs) / total if total else None

    grouped = Standing(
        profile_id=bots[0].profile_id,
        name="Random Bot",
        model_id=BOT_MODEL_ID,
        rating=weighted(lambda s: s.rating) or 1000.0,
        games_played=games,
        win_rate=weighted(lambda s: s.win_rate),
        average_placement=weighted(lambda s: s.average_placement),
    )
    costs = [usage.get(s.profile_id, Usage()).cost_micro_eur for s in bots]
    combined = Usage(
        None if None in costs else sum(costs),
        sum(usage.get(s.profile_id, Usage()).accepted for s in bots),
        sum(usage.get(s.profile_id, Usage()).rejected for s in bots),
    )
    usage[grouped.profile_id] = combined
    return (grouped, len(bots)), rest


@router.get("/leaderboard")
async def leaderboard(
    request: Request,
    store: Store,
    game: Annotated[str | None, Query(description="A game id; omit for the overall rating")] = None,
    kind: Annotated[
        Literal["models", "bots", "all"] | None,
        Query(description="Real models, random bots or all; default real models, or all if none"),
    ] = None,
    group_bots: Annotated[
        bool, Query(description="One row for all random-bot seats; false lists every seat")
    ] = True,
    demo: Annotated[
        bool, Query(description="Include the demo profiles (random bots from demo_seed)")
    ] = False,
) -> Leaderboard:
    """Players by rating, best first: in one game, or overall across all games.

    By default only real models are ranked; when none is rated yet everyone is shown and
    `fallback` is true. The seats of random bots are grouped into one "Random Bot" row
    unless `group_bots=false`.
    """
    standings = await store.leaderboard(game, demo=demo)
    live: LiveMatches = request.app.state.live
    usage = await store.usage(live.ledger, game)
    grouped, others = group_seat_bots(standings, usage) if group_bots else (None, standings)
    entries: list[tuple[Standing, str, int]] = [
        (s, "bot" if s.model_id == BOT_MODEL_ID else "model", 1) for s in others
    ]
    if grouped:
        entries.append((grouped[0], "bot", grouped[1]))
    counts = {
        "models": sum(1 for _, k, _ in entries if k == "model"),
        "bots": sum(1 for _, k, _ in entries if k == "bot"),
    }
    shown, fallback = kind or "models", False
    if kind is None and counts["models"] == 0:
        shown, fallback = "all", True
    wanted = {"models": ("model",), "bots": ("bot",), "all": ("model", "bot")}[shown]
    entries = sorted(
        (e for e in entries if e[1] in wanted), key=lambda e: (-e[0].rating, e[0].name)
    )
    rows = []
    for position, (s, row_kind, members) in enumerate(entries, start=1):
        used = usage.get(s.profile_id, Usage())
        answers = used.accepted + used.rejected
        rows.append(
            LeaderboardRow(
                rank=position,
                kind=row_kind,
                vendor=vendor_of(s.model_id) if row_kind == "model" else None,
                members=members,
                cost_per_game_micro_eur=(
                    round(used.cost_micro_eur / s.games_played)
                    if s.games_played and used.cost_micro_eur
                    else None
                ),
                tool_error_rate=used.rejected / answers if answers else None,
                **StandingOut.of(s).model_dump(),
            )
        )
    return Leaderboard(
        game=game,
        games=await store.rated_games(),
        kind=shown,
        fallback=fallback,
        counts=counts,
        show_demo=demo,
        demo_hidden=0 if demo else await store.demo_profiles(),
        rows=rows,
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
