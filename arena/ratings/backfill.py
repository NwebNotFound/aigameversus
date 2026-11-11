"""Rate the model matches that were played before model matches were rated (D-081).

    DATABASE_URL=... uv run arena ratings backfill

Every finished match with a result and a model in a seat that no rating has counted is rated
now, oldest first, the way a new match is rated. Idempotent: a second run finds nothing.
Includes matches imported from the example files. Costs nothing: no model is called.
"""

from dataclasses import dataclass, field
from typing import Any

from arena.db.match_store import MatchStore
from arena.ratings.store import RatingStore


@dataclass
class Backfill:
    rated: int = 0
    unrated: list[str] = field(default_factory=list)  # one sentence per match left unrated


async def backfill_model_ratings(pool: Any) -> Backfill:
    """Rate every unrated finished model match; return how many, and why others stay unrated."""
    done = Backfill()
    store = RatingStore(pool)
    for record in await MatchStore(pool).unrated_model_matches():
        models = {seat: s.model_id for seat, s in (record.seats or {}).items() if s.model_id}
        if set(models) != set(record.players) or not record.placements:
            done.unrated.append(f"{record.id}: not every seat had a model")
            continue
        result = await store.rate_model_match(record.id, record.game, models, record.placements)
        if isinstance(result, str):
            done.unrated.append(f"{record.id}: {result}")
        else:
            done.rated += 1
    return done
