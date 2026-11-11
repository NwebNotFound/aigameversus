"""Player profiles and ratings in Postgres."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

import asyncpg

from arena.engine.types import Placement
from arena.ratings.elo import DEFAULT_K, RatingChange, overall_rating, update_ratings
from arena.ratings.stats import win_rate

BOT_MODEL_ID = "random-bot"


@dataclass(frozen=True)
class GameRating:
    rating: float
    games_played: int


# Placements with the game they were played in.
_PLACEMENTS_BY_GAME = (
    "SELECT mp.match_id, mp.profile_id, mp.rank, rm.game_id "
    "FROM match_placements mp JOIN rated_matches rm ON rm.match_id = mp.match_id"
)


@dataclass(frozen=True)
class Standing:
    profile_id: UUID
    name: str
    model_id: str
    rating: float
    games_played: int
    win_rate: float | None
    average_placement: float | None


@dataclass(frozen=True)
class MatchResult:
    match_id: UUID
    game_id: str
    rated_at: datetime
    rank: int
    players: int
    rating_change: float


@dataclass(frozen=True)
class Profile:
    profile_id: UUID
    name: str
    model_id: str
    personality_id: str | None
    overall: Standing | None
    per_game: dict[str, Standing]
    recent_matches: list[MatchResult]


class RatingStore:
    def __init__(self, pool: asyncpg.Pool, k: float = DEFAULT_K):
        self._pool = pool
        self._k = k

    async def create_profile(
        self,
        name: str,
        model_id: str,
        personality_id: str | None = None,
        profile_id: UUID | None = None,
    ) -> UUID:
        """Add a profile; a random id unless `profile_id` is given."""
        profile_id = profile_id or uuid4()
        await self._pool.execute(
            "INSERT INTO player_profiles (id, name, model_id, personality_id) "
            "VALUES ($1, $2, $3, $4)",
            profile_id,
            name,
            model_id,
            personality_id,
        )
        return profile_id

    async def model_profile(self, model_id: str, personality_id: str | None = None) -> UUID:
        """The profile of a model with a personality, created on first use (D-081).

        One profile per model and personality, the same in every match and every seat, so
        its rating, statistics and cost add up. The id derives from both, so it never changes.
        """
        profile_id = uuid5(NAMESPACE_URL, f"aigameversus/model/{model_id}/{personality_id or ''}")
        await self._pool.execute(
            "INSERT INTO player_profiles (id, name, model_id, personality_id) "
            "VALUES ($1, $2, $3, $4) ON CONFLICT (id) DO NOTHING",
            profile_id,
            model_id,
            model_id,
            personality_id,
        )
        return profile_id

    async def bot_profiles(self, seats: Sequence[str]) -> dict[str, UUID]:
        """The profile of the random bot on each seat, created on first use (D-052).

        One profile per seat name ("Random Bot p1"), because a match rates every
        profile once. The id derives from the seat, so it is the same every time.
        """
        ids = {
            seat: uuid5(NAMESPACE_URL, f"aigameversus/bot/{BOT_MODEL_ID}/{seat}") for seat in seats
        }
        await self._pool.executemany(
            "INSERT INTO player_profiles (id, name, model_id) VALUES ($1, $2, $3) "
            "ON CONFLICT (id) DO NOTHING",
            [(profile_id, f"Random Bot {seat}", BOT_MODEL_ID) for seat, profile_id in ids.items()],
        )
        return ids

    async def ratings(self, profile_id: UUID) -> dict[str, GameRating]:
        """The profile's rating in every game it has played, by game id."""
        rows = await self._pool.fetch(
            "SELECT game_id, rating, games_played FROM ratings WHERE profile_id = $1",
            profile_id,
        )
        return {row["game_id"]: GameRating(row["rating"], row["games_played"]) for row in rows}

    async def overall(self, profile_id: UUID) -> float:
        """Per-game ratings averaged, weighted by games played."""
        per_game = await self.ratings(profile_id)
        return overall_rating({g: (r.rating, r.games_played) for g, r in per_game.items()})

    async def apply_match_result(
        self,
        match_id: UUID,
        game_id: str,
        placements: Sequence[Placement],
        seats: Mapping[str, UUID] | None = None,
    ) -> dict[str, RatingChange] | None:
        """Update the ratings of a finished match; `Placement.player` is a profile id.

        `seats` maps the player ids of the match log to these profiles; it is
        stored with the result, so the profile's statistics can be read from
        the log later. Idempotent: a match already applied changes nothing and
        returns None. All updates of one match happen in one transaction.
        """
        # Canonical id text, so "ABC..." and "abc..." are the same player.
        placements = [Placement(player=str(UUID(p.player)), rank=p.rank) for p in placements]
        profile_ids = sorted(UUID(placement.player) for placement in placements)
        if seats is not None and sorted(seats.values()) != profile_ids:
            raise ValueError("seats must name each placed profile once")
        async with self._pool.acquire() as connection, connection.transaction():
            claimed = await connection.fetchval(
                "INSERT INTO rated_matches (match_id, game_id) VALUES ($1, $2) "
                "ON CONFLICT (match_id) DO NOTHING RETURNING match_id",
                match_id,
                game_id,
            )
            if claimed is None:
                return None
            # Create missing rows first, so every row can be locked against a parallel match.
            # Both steps go in profile-id order, so two matches cannot deadlock.
            await connection.executemany(
                "INSERT INTO ratings (profile_id, game_id) VALUES ($1, $2) ON CONFLICT DO NOTHING",
                [(profile_id, game_id) for profile_id in profile_ids],
            )
            rows = await connection.fetch(
                "SELECT profile_id, rating FROM ratings "
                "WHERE game_id = $1 AND profile_id = ANY($2::uuid[]) "
                "ORDER BY profile_id FOR UPDATE",
                game_id,
                profile_ids,
            )
            current = {str(row["profile_id"]): row["rating"] for row in rows}
            changes = update_ratings(current, placements, self._k)
            await connection.executemany(
                "UPDATE ratings SET rating = $3, games_played = games_played + 1, "
                "updated_at = now() WHERE profile_id = $1 AND game_id = $2",
                [(UUID(player), game_id, change.after) for player, change in changes.items()],
            )
            if seats is not None:
                await connection.executemany(
                    "INSERT INTO match_seats (match_id, seat, profile_id) VALUES ($1, $2, $3)",
                    [(match_id, seat, profile_id) for seat, profile_id in seats.items()],
                )
            rank = {placement.player: placement.rank for placement in placements}
            await connection.executemany(
                "INSERT INTO match_placements "
                "(match_id, profile_id, rank, players, rating_before, rating_after) "
                "VALUES ($1, $2, $3, $4, $5, $6)",
                [
                    (match_id, UUID(player), rank[player], len(placements), c.before, c.after)
                    for player, c in changes.items()
                ],
            )
            return changes

    async def seats(self, profile_id: UUID) -> dict[str, list[tuple[UUID, str]]]:
        """The rated matches a profile played, by game id: (match id, seat), oldest first."""
        rows = await self._pool.fetch(
            "SELECT rm.game_id, s.match_id, s.seat FROM match_seats s "
            "JOIN rated_matches rm ON rm.match_id = s.match_id "
            "WHERE s.profile_id = $1 ORDER BY rm.rated_at, s.match_id",
            profile_id,
        )
        played: dict[str, list[tuple[UUID, str]]] = {}
        for row in rows:
            played.setdefault(row["game_id"], []).append((row["match_id"], row["seat"]))
        return played

    async def rated_games(self) -> list[str]:
        """Ids of the games that have at least one rated match, sorted."""
        rows = await self._pool.fetch("SELECT DISTINCT game_id FROM ratings ORDER BY game_id")
        return [row["game_id"] for row in rows]

    async def leaderboard(self, game_id: str | None = None) -> list[Standing]:
        """Everyone with at least one rated match, best first.

        With `game_id` the rating of that game; without it the overall rating.
        """
        rows = await self._pool.fetch(
            "SELECT p.id, p.name, p.model_id, r.game_id, r.rating, r.games_played, "
            "count(mp.match_id) FILTER (WHERE mp.rank = 1) AS wins, "
            "coalesce(sum(mp.rank), 0) AS rank_sum "
            "FROM ratings r JOIN player_profiles p ON p.id = r.profile_id "
            f"LEFT JOIN ({_PLACEMENTS_BY_GAME}) mp "
            "  ON mp.profile_id = r.profile_id AND mp.game_id = r.game_id "
            "WHERE r.games_played > 0 AND ($1::text IS NULL OR r.game_id = $1) "
            "GROUP BY p.id, p.name, p.model_id, r.game_id, r.rating, r.games_played",
            game_id,
        )
        by_profile: dict[UUID, list[asyncpg.Record]] = {}
        for row in rows:
            by_profile.setdefault(row["id"], []).append(row)
        standings = [_standing(group) for group in by_profile.values()]
        return sorted(standings, key=lambda s: (-s.rating, s.name, str(s.profile_id)))

    async def profile(self, profile_id: UUID, recent: int = 10) -> Profile | None:
        """A profile with its rating per game and its latest matches; None if unknown."""
        row = await self._pool.fetchrow(
            "SELECT id, name, model_id, personality_id FROM player_profiles WHERE id = $1",
            profile_id,
        )
        if row is None:
            return None
        games = await self._pool.fetch(
            "SELECT r.game_id, r.rating, r.games_played, "
            "count(mp.match_id) FILTER (WHERE mp.rank = 1) AS wins, "
            "coalesce(sum(mp.rank), 0) AS rank_sum, p.id, p.name, p.model_id "
            "FROM ratings r JOIN player_profiles p ON p.id = r.profile_id "
            f"LEFT JOIN ({_PLACEMENTS_BY_GAME}) mp "
            "  ON mp.profile_id = r.profile_id AND mp.game_id = r.game_id "
            "WHERE r.profile_id = $1 AND r.games_played > 0 "
            "GROUP BY r.game_id, r.rating, r.games_played, p.id, p.name, p.model_id "
            "ORDER BY r.game_id",
            profile_id,
        )
        matches = await self._pool.fetch(
            "SELECT rm.match_id, rm.game_id, rm.rated_at, mp.rank, mp.players, "
            "mp.rating_before, mp.rating_after "
            "FROM match_placements mp JOIN rated_matches rm ON rm.match_id = mp.match_id "
            "WHERE mp.profile_id = $1 ORDER BY rm.rated_at DESC, rm.match_id LIMIT $2",
            profile_id,
            recent,
        )
        return Profile(
            profile_id=row["id"],
            name=row["name"],
            model_id=row["model_id"],
            personality_id=row["personality_id"],
            overall=_standing(games) if games else None,
            per_game={g["game_id"]: _standing([g]) for g in games},
            recent_matches=[
                MatchResult(
                    match_id=m["match_id"],
                    game_id=m["game_id"],
                    rated_at=m["rated_at"],
                    rank=m["rank"],
                    players=m["players"],
                    rating_change=m["rating_after"] - m["rating_before"],
                )
                for m in matches
            ],
        )


def _standing(rows: Sequence[asyncpg.Record]) -> Standing:
    """One standing from a profile's rating rows: one row for a game, several for overall."""
    games = sum(row["games_played"] for row in rows)
    wins = sum(row["wins"] for row in rows)
    rank_sum = sum(row["rank_sum"] for row in rows)
    first = rows[0]
    return Standing(
        profile_id=first["id"],
        name=first["name"],
        model_id=first["model_id"],
        rating=overall_rating(
            {row["game_id"]: (row["rating"], row["games_played"]) for row in rows}
        ),
        games_played=games,
        win_rate=win_rate(wins, games),
        average_placement=rank_sum / games if games else None,
    )
