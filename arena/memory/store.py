"""Relationships between profiles in Postgres."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from uuid import UUID

import asyncpg

from arena.engine.types import Event, PlayerId
from arena.memory.facts import match_facts
from arena.memory.trust import TrustRules, load_rules, match_changes


@dataclass(frozen=True)
class Note:
    match_id: UUID
    game_id: str
    text: str


@dataclass(frozen=True)
class Relationship:
    other_id: UUID
    name: str
    model_id: str
    trust: int
    notes: list[Note]


class MemoryStore:
    def __init__(self, pool: asyncpg.Pool, rules: TrustRules | None = None):
        self._pool = pool
        self._rules = rules or load_rules()

    async def remember_match(
        self,
        match_id: UUID,
        game_id: str,
        events: Sequence[Event],
        seats: Mapping[PlayerId, UUID],
    ) -> bool:
        """Add a finished match's facts to the relationships of its seated profiles.

        `seats` maps the player ids of the log to profiles. Idempotent: a match
        already remembered changes nothing and returns False. All updates of a
        match happen in one transaction.
        """
        changes = match_changes(game_id, match_facts(game_id, events, list(seats)), self._rules)
        pairs = sorted((seats[o], seats[a], change) for (o, a), change in changes.items())
        async with self._pool.acquire() as connection, connection.transaction():
            claimed = await connection.fetchval(
                "INSERT INTO remembered_matches (match_id, game_id) VALUES ($1, $2) "
                "ON CONFLICT (match_id) DO NOTHING RETURNING match_id",
                match_id,
                game_id,
            )
            if claimed is None:
                return False
            # In (profile, other) order, so two matches cannot deadlock.
            for profile_id, other_id, change in pairs:
                current = await connection.fetchrow(
                    "INSERT INTO relationships (profile_id, other_id) VALUES ($1, $2) "
                    "ON CONFLICT (profile_id, other_id) DO UPDATE SET trust = relationships.trust "
                    "RETURNING trust, notes",
                    profile_id,
                    other_id,
                )
                new_notes = [
                    {"match_id": str(match_id), "game_id": game_id, "text": text}
                    for text in reversed(change.notes)
                ]
                notes = (new_notes + list(current["notes"]))[: self._rules.limits.notes]
                await connection.execute(
                    "UPDATE relationships SET trust = $3, notes = $4, updated_at = now() "
                    "WHERE profile_id = $1 AND other_id = $2",
                    profile_id,
                    other_id,
                    self._rules.clamp(current["trust"] + change.trust),
                    notes,
                )
            return True

    async def relationships(self, profile_id: UUID) -> list[Relationship]:
        """What a profile thinks of the others: strongest feeling first, then by name."""
        rows = await self._pool.fetch(
            "SELECT r.other_id, p.name, p.model_id, r.trust, r.notes FROM relationships r "
            "JOIN player_profiles p ON p.id = r.other_id WHERE r.profile_id = $1 "
            "ORDER BY abs(r.trust) DESC, p.name, r.other_id",
            profile_id,
        )
        return [
            Relationship(
                other_id=row["other_id"],
                name=row["name"],
                model_id=row["model_id"],
                trust=row["trust"],
                notes=[Note(UUID(n["match_id"]), n["game_id"], n["text"]) for n in row["notes"]],
            )
            for row in rows
        ]
