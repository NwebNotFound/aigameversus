"""Player profiles and ratings in Postgres."""

from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID, uuid4

import asyncpg

from arena.engine.types import Placement
from arena.ratings.elo import DEFAULT_K, RatingChange, overall_rating, update_ratings


@dataclass(frozen=True)
class GameRating:
    rating: float
    games_played: int


class RatingStore:
    def __init__(self, pool: asyncpg.Pool, k: float = DEFAULT_K):
        self._pool = pool
        self._k = k

    async def create_profile(
        self, name: str, model_id: str, personality_id: str | None = None
    ) -> UUID:
        profile_id = uuid4()
        await self._pool.execute(
            "INSERT INTO player_profiles (id, name, model_id, personality_id) "
            "VALUES ($1, $2, $3, $4)",
            profile_id,
            name,
            model_id,
            personality_id,
        )
        return profile_id

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
        self, match_id: UUID, game_id: str, placements: Sequence[Placement]
    ) -> dict[str, RatingChange] | None:
        """Update the ratings of a finished match; `Placement.player` is a profile id.

        Idempotent: a match already applied changes nothing and returns None.
        All updates of one match happen in one transaction.
        """
        # Canonical id text, so "ABC..." and "abc..." are the same player.
        placements = [Placement(player=str(UUID(p.player)), rank=p.rank) for p in placements]
        profile_ids = sorted(UUID(placement.player) for placement in placements)
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
            return changes
