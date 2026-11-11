"""Relationships and match memories of profiles in Postgres."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

import asyncpg

from arena.engine.types import Event, Placement, PlayerId
from arena.memory.facts import match_facts
from arena.memory.summary import MatchView, Summarizer, TemplateSummarizer
from arena.memory.trust import TrustRules, load_rules, match_changes


@dataclass(frozen=True)
class Note:
    match_id: UUID
    game_id: str
    text: str


@dataclass(frozen=True)
class MatchMemory:
    match_id: UUID
    game_id: str
    summary: str
    created_at: datetime


@dataclass(frozen=True)
class Reset:
    relationships: int
    memories: int


@dataclass(frozen=True)
class Relationship:
    other_id: UUID
    name: str
    model_id: str
    trust: int
    notes: list[Note]


class MemoryStore:
    def __init__(
        self,
        pool: asyncpg.Pool,
        rules: TrustRules | None = None,
        summarizer: Summarizer | None = None,
    ):
        self._pool = pool
        self._rules = rules or load_rules()
        self._summarizer = summarizer or TemplateSummarizer(self._rules)

    async def remember_match(
        self,
        match_id: UUID,
        game_id: str,
        events: Sequence[Event],
        seats: Mapping[PlayerId, UUID],
        game_name: str | None = None,
    ) -> bool:
        """Add a finished match to the memory of its seated profiles.

        Its facts change their relationships, and each profile gets a summary
        of the match from its own view. `seats` maps the player ids of the log
        to profiles. Idempotent: a match already remembered changes nothing and
        returns False. All updates of a match happen in one transaction.
        """
        facts = match_facts(game_id, events, list(seats))
        changes = match_changes(game_id, facts, self._rules)
        pairs = sorted((seats[o], seats[a], change) for (o, a), change in changes.items())
        finished = next((e for e in reversed(events) if e.type == "match_finished"), None)
        placements = [Placement(**p) for p in finished.data["placements"]] if finished else []
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
            rows = await connection.fetch(
                "SELECT id, name FROM player_profiles WHERE id = ANY($1::uuid[])",
                list(seats.values()),
            )
            name_of = {row["id"]: row["name"] for row in rows}
            names = {seat: name_of[profile_id] for seat, profile_id in seats.items()}
            for seat, profile_id in sorted(seats.items(), key=lambda s: s[1]):
                view = MatchView(
                    game_name=game_name or game_id,
                    game_id=game_id,
                    me=seat,
                    names=names,
                    placements=placements,
                    facts=[fact for fact in facts if fact.observer == seat],
                )
                await connection.execute(
                    "INSERT INTO match_memories (profile_id, match_id, game_id, opponents, "
                    "summary) VALUES ($1, $2, $3, $4, $5)",
                    profile_id,
                    match_id,
                    game_id,
                    [other for other in seats.values() if other != profile_id],
                    self._summarizer.summarize(view),
                )
            return True

    async def memories_with(
        self, profile_id: UUID, opponents: Sequence[UUID], limit: int = 10
    ) -> list[MatchMemory]:
        """The profile's summaries of matches against any of `opponents`, newest first."""
        rows = await self._pool.fetch(
            "SELECT match_id, game_id, summary, created_at FROM match_memories "
            "WHERE profile_id = $1 AND opponents && $2::uuid[] "
            "ORDER BY created_at DESC, match_id LIMIT $3",
            profile_id,
            list(opponents),
            limit,
        )
        return [MatchMemory(**row) for row in rows]

    async def memories(self, profile_id: UUID, limit: int = 20) -> list[MatchMemory]:
        """The profile's newest match summaries."""
        rows = await self._pool.fetch(
            "SELECT match_id, game_id, summary, created_at FROM match_memories "
            "WHERE profile_id = $1 ORDER BY created_at DESC, match_id LIMIT $2",
            profile_id,
            limit,
        )
        return [MatchMemory(**row) for row in rows]

    async def reset(self, profile_id: UUID | None = None) -> Reset:
        """Forget: every profile's memory, or only what one profile remembers.

        Matches already remembered stay claimed, so a reset cannot make an old
        match count again.
        """
        async with self._pool.acquire() as connection, connection.transaction():
            if profile_id is None:
                relationships = await connection.execute("DELETE FROM relationships")
                memories = await connection.execute("DELETE FROM match_memories")
            else:
                relationships = await connection.execute(
                    "DELETE FROM relationships WHERE profile_id = $1", profile_id
                )
                memories = await connection.execute(
                    "DELETE FROM match_memories WHERE profile_id = $1", profile_id
                )
        return Reset(relationships=_count(relationships), memories=_count(memories))

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


def _count(status: str) -> int:
    """Rows of a `DELETE n` command status."""
    return int(status.rsplit(" ", 1)[-1])
