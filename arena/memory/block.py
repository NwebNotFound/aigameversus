"""The memory a player brings to a match: what it remembers of the opponents at the table.

Only the player's own relationships and summaries are read, and only about the
profiles actually seated. Strongest feelings come first, then the newest
matches; the block stops at the first line that does not fit `MEMORY_CHARS`.
"""

from collections.abc import Mapping
from uuid import UUID

from arena.engine.types import PlayerId
from arena.memory.store import MemoryStore

MEMORY_CHARS = 1200  # the block never gets longer than this
NOTES_PER_PLAYER = 3
MATCHES = 5


async def memory_block(
    store: MemoryStore, me: UUID, opponents: Mapping[PlayerId, UUID]
) -> str | None:
    """The memory block for the player with profile `me`; None if it remembers nobody here.

    `opponents` maps the other seats of this match to their profiles.
    """
    seat_of = {profile: seat for seat, profile in opponents.items() if profile != me}
    if not seat_of:
        return None
    lines: list[str] = []
    for relation in await store.relationships(me):
        seat = seat_of.get(relation.other_id)
        if seat is None:
            continue
        line = f"- {seat} (you know them as {relation.name}): trust {relation.trust:+d}"
        notes = [note.text for note in relation.notes[:NOTES_PER_PLAYER]]
        lines.append(line + (". " + "; ".join(notes) + "." if notes else "."))
    past = await store.memories_with(me, list(seat_of), limit=MATCHES)
    if past:
        lines.append("Earlier matches against them, newest first:")
        lines += [f"- {memory.summary}" for memory in past]
    if not lines:
        return None
    return _fit(lines)


def _fit(lines: list[str]) -> str:
    """The first lines that fit the cap together; nothing is cut in the middle."""
    kept: list[str] = []
    used = 0
    for line in lines:
        if used + len(line) + 1 > MEMORY_CHARS:
            break
        kept.append(line)
        used += len(line) + 1
    return "\n".join(kept)
