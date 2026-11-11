"""Fill the ratings tables with DEMO profiles, so the leaderboard has something to show.

    DATABASE_URL=postgresql://arena:arena_dev@127.0.0.1:5433/arena \\
        uv run python -m arena.ratings.demo_seed --matches 40

Every profile is named "DEMO …" and plays as a random bot in real High Card
matches (`games/toy`), so no model is called. The match ids derive from the
seed: running it twice with the same seed adds nothing. It refuses to touch a
database that has any profile not named "DEMO …". For local development only.
"""

import argparse
import asyncio
import os
import random
import sys
from uuid import NAMESPACE_URL, UUID, uuid5

import asyncpg

from arena.agents.random_bot import random_bots
from arena.db.database import connect, migrate
from arena.engine.match import Match
from arena.ratings.store import RatingStore
from games.toy.plugin import ToyGame

DEMO_PREFIX = "DEMO "
DEMO_MODEL = "random-bot"
DEMO_NAMES = [f"{DEMO_PREFIX}{name}" for name in ("Ada", "Basil", "Cleo", "Dov", "Elin", "Faro")]
GAME_ID = ToyGame.id


class RefusedError(RuntimeError):
    """The database holds profiles that are not demo data."""


async def seed_demo(pool: asyncpg.Pool, matches: int = 40, seed: int = 1) -> int:
    """Play `matches` random-bot matches between the demo profiles; return how many were new."""
    real = await pool.fetchval(
        "SELECT count(*) FROM player_profiles WHERE name NOT LIKE $1", DEMO_PREFIX + "%"
    )
    if real:
        raise RefusedError(f"{real} profile(s) are not demo data; refusing to add demo matches")

    store = RatingStore(pool)
    profile_ids = await _demo_profiles(pool, store)
    plugin = ToyGame()
    rng = random.Random(seed)
    applied = 0
    for number in range(matches):
        players = rng.sample(profile_ids, rng.randint(plugin.min_players, plugin.max_players))
        match_seed = rng.randrange(2**31)
        match = Match(plugin, random_bots(plugin, players, match_seed), seed=match_seed)
        placements = await match.run()
        match_id = uuid5(NAMESPACE_URL, f"aigameversus-demo/{seed}/{number}")
        if await store.apply_match_result(match_id, GAME_ID, placements) is not None:
            applied += 1
    return applied


async def _demo_profiles(pool: asyncpg.Pool, store: RatingStore) -> list[str]:
    """The demo profiles, created on first use; ids as text, in name order."""
    existing = {
        row["name"]: row["id"]
        for row in await pool.fetch(
            "SELECT id, name FROM player_profiles WHERE name = ANY($1::text[])", DEMO_NAMES
        )
    }
    ids: list[UUID] = []
    for name in DEMO_NAMES:
        # Fixed ids: bots draw their moves from streams keyed by player id.
        demo_id = uuid5(NAMESPACE_URL, f"aigameversus-demo/profile/{name}")
        ids.append(
            existing.get(name) or await store.create_profile(name, DEMO_MODEL, None, demo_id)
        )
    return [str(profile_id) for profile_id in ids]


async def _main(matches: int, seed: int) -> int:
    pool = await connect(os.environ["DATABASE_URL"])
    try:
        await migrate(pool)
        applied = await seed_demo(pool, matches, seed)
    except RefusedError as error:
        print(f"demo_seed: {error}", file=sys.stderr)
        return 1
    finally:
        await pool.close()
    print(f"demo_seed: {applied} new demo match(es) rated for {len(DEMO_NAMES)} DEMO profiles")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--matches", type=int, default=40, help="matches to play (default 40)")
    parser.add_argument("--seed", type=int, default=1, help="seed; same seed, same matches")
    args = parser.parse_args()
    if "DATABASE_URL" not in os.environ:
        parser.error("set DATABASE_URL to the local development database")
    sys.exit(asyncio.run(_main(args.matches, args.seed)))


if __name__ == "__main__":
    main()
