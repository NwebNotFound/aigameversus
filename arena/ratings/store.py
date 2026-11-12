"""Player profiles and ratings in Postgres."""

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Literal
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

import asyncpg

from arena.db.ledger import Ledger, LedgerUnavailable
from arena.engine.types import Placement
from arena.ratings.elo import DEFAULT_K, RatingChange, overall_rating, update_ratings
from arena.ratings.stats import win_rate

BOT_MODEL_ID = "random-bot"


@dataclass(frozen=True)
class Usage:
    """What a profile cost and how often the server refused its answers, in rated matches."""

    cost_micro_eur: int | None = 0  # None while the ledger cannot be read
    accepted: int = 0  # answers the server took
    rejected: int = 0  # answers the server refused (a wrong tool, bad arguments, an illegal move)
    # moves taken as answers whose garbled call was read anyway (answer_repair); at most `accepted`
    repaired: int = 0


@dataclass(frozen=True)
class Unrated:
    """What one model played in one game without a rating: finished matches the rating skipped."""

    model_id: str
    game: str
    matches_played: int  # finished matches with the model in a seat
    matches_rated: int  # of those, the ones a rating counted
    reasons: dict[str, int]  # why the others were not rated: reason code -> matches


# Why a finished model match has no rating (codes of `Unrated.reasons`).
DUPLICATE_MODEL = "duplicate_model"  # this model sat in several seats of the match
TABLE_REPEATS_A_MODEL = "table_repeats_a_model"  # another model did: the whole table is unrated
FEWER_THAN_TWO_MODELS = "fewer_than_two_models"  # one model among random bots: no one to rank
NOT_RATED = "not_rated"  # none of the above: the match was not rated and the log does not say why


def unrated_reason(seat_models: Mapping[str, str], model_id: str) -> str:
    """Why a finished, unrated match did not count for `model_id` (D-081 rules)."""
    counts = Counter(seat_models.values())
    if counts[model_id] > 1:
        return DUPLICATE_MODEL
    if any(n > 1 for n in counts.values()):
        return TABLE_REPEATS_A_MODEL
    if len(counts) < 2:
        return FEWER_THAN_TWO_MODELS
    return NOT_RATED


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
    played_at: datetime  # when the match itself ended (not when its rating was applied)
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
        is_demo: bool = False,
    ) -> UUID:
        """Add a profile; a random id unless `profile_id` is given. Demo profiles are hidden."""
        profile_id = profile_id or uuid4()
        await self._pool.execute(
            "INSERT INTO player_profiles (id, name, model_id, personality_id, is_demo) "
            "VALUES ($1, $2, $3, $4, $5)",
            profile_id,
            name,
            model_id,
            personality_id,
            is_demo,
        )
        return profile_id

    async def model_profile(self, model_id: str, personality_id: str | None = None) -> UUID:
        """The profile of a model with a personality, created on first use (D-081).

        One profile per model and personality, the same in every match and every seat, so
        its rating, statistics and cost add up. The id derives from both, so it never changes.
        """
        profile_id = self.model_profile_id(model_id, personality_id)
        await self._pool.execute(
            "INSERT INTO player_profiles (id, name, model_id, personality_id) "
            "VALUES ($1, $2, $3, $4) ON CONFLICT (id) DO NOTHING",
            profile_id,
            model_id,
            model_id,
            personality_id,
        )
        return profile_id

    def model_profile_id(self, model_id: str, personality_id: str | None = None) -> UUID:
        """The id `model_profile` gives, without creating the profile."""
        return uuid5(NAMESPACE_URL, f"aigameversus/model/{model_id}/{personality_id or ''}")

    async def other_personalities(self, model_id: str) -> list[tuple[UUID, str]]:
        """The profiles of a model that play with a personality: (profile id, personality id)."""
        rows = await self._pool.fetch(
            "SELECT id, personality_id FROM player_profiles "
            "WHERE model_id = $1 AND personality_id IS NOT NULL ORDER BY personality_id",
            model_id,
        )
        return [(row["id"], row["personality_id"]) for row in rows]

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

    async def rate_model_match(
        self,
        match_id: UUID,
        game_id: str,
        models: Mapping[str, str],
        placements: Sequence[Placement],
    ) -> dict[str, UUID] | str:
        """Rate a finished model match: one profile per model, the same in every match (D-081).

        `models` maps each seat to its model id. Returns the seat to profile mapping, or a
        sentence when the match is not rated: a profile is rated once per match, so a model
        in several seats leaves the match unrated. Idempotent by match id.
        """
        names = list(models.values())
        if len(set(names)) != len(names):
            repeated = sorted({m for m in names if names.count(m) > 1})
            return (
                f"Not rated: {', '.join(repeated)} sits in several seats, "
                "and a model is rated once per match"
            )
        profiles = {seat: await self.model_profile(model) for seat, model in models.items()}
        await self.apply_match_result(
            match_id,
            game_id,
            [Placement(player=str(profiles[p.player]), rank=p.rank) for p in placements],
            seats=profiles,
        )
        return profiles

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

    async def usage(
        self, ledger: Ledger, game_id: str | None = None, profile_id: UUID | None = None
    ) -> dict[UUID, Usage]:
        """Cost and answer counts per profile, from the ledger and the stored event logs.

        Counts the rated matches of `game_id`, or of every game. Cost is the sum of the booked
        model calls of the profile's seats, read from `ledger` (its own database or this one),
        and None for everyone while the ledger cannot be read; answers are the engine's
        `action_accepted` and `action_rejected` events of those seats, and the moves whose
        `decision` names a repair. Profiles without a seat
        are left out. With `profile_id` only that profile is counted, which makes the query
        much smaller.
        """
        seats_sql = (
            "SELECT s.match_id, s.seat, s.profile_id FROM match_seats s "
            "JOIN rated_matches rm ON rm.match_id = s.match_id "
            "WHERE ($1::text IS NULL OR rm.game_id = $1) "
            "  AND ($2::uuid IS NULL OR s.profile_id = $2)"
        )
        seats = await self._pool.fetch(seats_sql, game_id, profile_id)
        answers = await self._pool.fetch(
            f"WITH seats AS ({seats_sql}) "
            "SELECT s.profile_id, "
            "  count(*) FILTER (WHERE e.type = 'action_accepted') AS accepted, "
            "  count(*) FILTER (WHERE e.type = 'action_rejected') AS rejected, "
            "  count(*) FILTER (WHERE e.type = 'decision' "
            "    AND e.data->>'fallback' IS NULL "  # a random move is no repaired answer
            "    AND jsonb_typeof(e.data->'repairs') = 'array' "
            "    AND jsonb_array_length(e.data->'repairs') > 0) AS repaired "
            "FROM seats s JOIN match_events e ON e.match_id = s.match_id "
            "  AND e.type IN ('action_accepted', 'action_rejected', 'decision') "
            "  AND e.data->>'player' = s.seat "
            "GROUP BY s.profile_id",
            game_id,
            profile_id,
        )
        try:
            booked = await ledger.seat_costs(sorted({seat["match_id"] for seat in seats}))
        except LedgerUnavailable:
            booked = None
        usage = {seat["profile_id"]: Usage(None if booked is None else 0) for seat in seats}
        for seat in seats:
            spent = usage[seat["profile_id"]]
            if booked is not None:
                cost = spent.cost_micro_eur + booked.get((seat["match_id"], seat["seat"]), 0)
                usage[seat["profile_id"]] = replace(spent, cost_micro_eur=cost)
        for row in answers:
            usage[row["profile_id"]] = replace(
                usage[row["profile_id"]],
                accepted=int(row["accepted"]),
                rejected=int(row["rejected"]),
                repaired=int(row["repaired"]),
            )
        return usage

    async def unrated_activity(
        self, game_id: str | None = None, model_id: str | None = None
    ) -> list[Unrated]:
        """Models with finished matches that no rating counted, per game: what and why.

        Read from the match records (the seats of finished matches) against `rated_matches`;
        no rating is invented. Only (model, game) pairs with at least one unrated match.
        """
        rows = await self._pool.fetch(
            "SELECT m.id, m.game, m.seats, r.match_id IS NOT NULL AS rated "
            "FROM matches m LEFT JOIN rated_matches r ON r.match_id = m.id "
            "WHERE m.status = 'finished' AND m.seats IS NOT NULL "
            "  AND ($1::text IS NULL OR m.game = $1)",
            game_id,
        )
        played: dict[tuple[str, str], int] = {}
        rated: dict[tuple[str, str], int] = {}
        reasons: dict[tuple[str, str], Counter[str]] = {}
        for row in rows:
            seats = row["seats"] or {}
            seat_models = {
                seat: info["model_id"]
                for seat, info in seats.items()
                if info.get("kind") == "model" and info.get("model_id")
            }
            for model in set(seat_models.values()):
                if model_id is not None and model != model_id:
                    continue
                key = (model, row["game"])
                played[key] = played.get(key, 0) + 1
                if row["rated"]:
                    rated[key] = rated.get(key, 0) + 1
                else:
                    reasons.setdefault(key, Counter())[unrated_reason(seat_models, model)] += 1
        return [
            Unrated(model, game, played[(model, game)], rated.get((model, game), 0), dict(why))
            for (model, game), why in sorted(reasons.items())
        ]

    async def demo_profiles(self) -> int:
        """How many rated demo profiles the leaderboard hides by default."""
        return await self._pool.fetchval(
            "SELECT count(DISTINCT p.id) FROM player_profiles p "
            "JOIN ratings r ON r.profile_id = p.id AND r.games_played > 0 WHERE p.is_demo"
        )

    async def rated_games(
        self, kind: Literal["models", "bots", "all"] = "all", *, demo: bool = True
    ) -> list[str]:
        """Ids of the games with at least one rated match of `kind`, sorted.

        `kind` limits it to real models or to random bots; demo profiles count only if `demo`.
        """
        rows = await self._pool.fetch(
            "SELECT DISTINCT r.game_id FROM ratings r "
            "JOIN player_profiles p ON p.id = r.profile_id "
            "WHERE r.games_played > 0 AND ($1 OR NOT p.is_demo) "
            "AND ($2 = 'all' OR ($2 = 'bots') = (p.model_id = $3)) "
            "ORDER BY r.game_id",
            demo,
            kind,
            BOT_MODEL_ID,
        )
        return [row["game_id"] for row in rows]

    async def leaderboard(
        self, game_id: str | None = None, *, demo: bool = False
    ) -> list[Standing]:
        """Everyone with at least one rated match, best first.

        With `game_id` the rating of that game; without it the overall rating. Demo profiles
        (`arena.ratings.demo_seed`) are left out unless `demo`.
        """
        rows = await self._pool.fetch(
            "SELECT p.id, p.name, p.model_id, r.game_id, r.rating, r.games_played, "
            "count(mp.match_id) FILTER (WHERE mp.rank = 1) AS wins, "
            "coalesce(sum(mp.rank), 0) AS rank_sum "
            "FROM ratings r JOIN player_profiles p ON p.id = r.profile_id "
            f"LEFT JOIN ({_PLACEMENTS_BY_GAME}) mp "
            "  ON mp.profile_id = r.profile_id AND mp.game_id = r.game_id "
            "WHERE r.games_played > 0 AND ($1::text IS NULL OR r.game_id = $1) "
            "  AND ($2 OR NOT p.is_demo) "
            "GROUP BY p.id, p.name, p.model_id, r.game_id, r.rating, r.games_played",
            game_id,
            demo,
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
            "mp.rating_before, mp.rating_after, "
            "coalesce(m.finished_at, m.started_at, rm.rated_at) AS played_at "
            "FROM match_placements mp JOIN rated_matches rm ON rm.match_id = mp.match_id "
            "LEFT JOIN matches m ON m.id = rm.match_id "
            "WHERE mp.profile_id = $1 ORDER BY played_at DESC, rm.match_id LIMIT $2",
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
                    played_at=m["played_at"],
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
