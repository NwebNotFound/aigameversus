import asyncio
import random
from uuid import uuid4

import asyncpg
import pytest

from arena.db.database import connect, migrate
from arena.engine.types import Placement
from arena.ratings.elo import START_RATING
from arena.ratings.store import GameRating, RatingStore


def run(database_url, scenario):
    """Run `scenario(store, pool)` against a migrated, empty schema."""

    async def go():
        pool = await connect(database_url)
        try:
            await migrate(pool)
            return await scenario(RatingStore(pool), pool)
        finally:
            await pool.close()

    return asyncio.run(go())


async def profiles(store: RatingStore, count: int) -> list[str]:
    return [str(await store.create_profile(f"p{i}", "mock-llm")) for i in range(count)]


def placed(players: list[str], ranks: list[int]) -> list[Placement]:
    return [Placement(player=p, rank=r) for p, r in zip(players, ranks, strict=True)]


def test_ratings_migration_applies_once(database_url):
    async def scenario(store, pool):
        again = await migrate(pool)
        tables = await pool.fetch(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = current_schema()"
        )
        return again, {row["table_name"] for row in tables}

    again, tables = run(database_url, scenario)

    assert again == []
    assert {"player_profiles", "ratings", "rated_matches"} <= tables


def test_first_match_rates_new_players_from_1000(database_url):
    async def scenario(store, pool):
        ann, bob = await profiles(store, 2)
        changes = await store.apply_match_result(uuid4(), "poker", placed([ann, bob], [1, 2]))
        return ann, bob, changes, await store.ratings(ann), await store.ratings(bob)

    ann, bob, changes, ann_ratings, bob_ratings = run(database_url, scenario)

    assert changes[ann].before == START_RATING
    assert ann_ratings == {"poker": GameRating(1016.0, 1)}
    assert bob_ratings == {"poker": GameRating(984.0, 1)}


def test_the_same_match_is_never_counted_twice(database_url):
    async def scenario(store, pool):
        ann, bob = await profiles(store, 2)
        match_id = uuid4()
        first = await store.apply_match_result(match_id, "poker", placed([ann, bob], [1, 2]))
        second = await store.apply_match_result(match_id, "poker", placed([ann, bob], [1, 2]))
        return first, second, await store.ratings(ann)

    first, second, ann_ratings = run(database_url, scenario)

    assert first is not None
    assert second is None
    assert ann_ratings == {"poker": GameRating(1016.0, 1)}


def test_ratings_build_up_per_game_and_overall(database_url):
    async def scenario(store, pool):
        ann, bob, cid = await profiles(store, 3)
        await store.apply_match_result(uuid4(), "poker", placed([ann, bob], [1, 2]))
        await store.apply_match_result(uuid4(), "poker", placed([ann, bob], [1, 2]))
        await store.apply_match_result(uuid4(), "werewolf", placed([ann, bob, cid], [3, 1, 1]))
        return await store.ratings(ann), await store.overall(ann)

    ann_ratings, overall = run(database_url, scenario)

    assert ann_ratings["poker"].games_played == 2
    assert ann_ratings["poker"].rating > 1016
    assert ann_ratings["werewolf"] == GameRating(984.0, 1)
    expected = (ann_ratings["poker"].rating * 2 + 984.0) / 3
    assert overall == pytest.approx(expected)


def test_a_failed_match_leaves_nothing_behind(database_url):
    async def scenario(store, pool):
        (ann,) = await profiles(store, 1)
        match_id = uuid4()
        with pytest.raises(asyncpg.ForeignKeyViolationError):
            await store.apply_match_result(match_id, "poker", placed([ann, str(uuid4())], [1, 2]))
        rated = await pool.fetchval("SELECT count(*) FROM rated_matches")
        return rated, await store.ratings(ann)

    rated, ann_ratings = run(database_url, scenario)

    assert rated == 0
    assert ann_ratings == {}


def test_player_ids_are_matched_case_insensitively(database_url):
    async def scenario(store, pool):
        ann, bob = await profiles(store, 2)
        await store.apply_match_result(uuid4(), "poker", placed([ann, bob], [1, 2]))
        await store.apply_match_result(uuid4(), "poker", placed([ann.upper(), bob], [1, 2]))
        return await store.ratings(ann)

    ann_ratings = run(database_url, scenario)

    assert ann_ratings["poker"].games_played == 2
    assert ann_ratings["poker"].rating > 1016


def test_parallel_matches_both_count(database_url):
    async def scenario(store, pool):
        ann, bob, cid = await profiles(store, 3)
        await asyncio.gather(
            store.apply_match_result(uuid4(), "poker", placed([ann, bob], [1, 2])),
            store.apply_match_result(uuid4(), "poker", placed([ann, cid], [1, 2])),
        )
        return await store.ratings(ann)

    ann_ratings = run(database_url, scenario)

    assert ann_ratings["poker"].games_played == 2


def test_concurrent_and_repeated_matches_neither_deadlock_nor_lose_updates(database_url):
    """120 overlapping calls: 60 matches among 8 profiles, each applied twice, in random order."""
    rng = random.Random(2026)

    async def scenario(store, pool):
        ids = await profiles(store, 8)
        jobs = []
        placements_total = 0
        for _ in range(60):
            players = rng.sample(ids, rng.randint(2, 6))
            ranks = [rng.randint(1, len(players)) for _ in players]
            placements_total += len(players)
            match_id = uuid4()
            jobs += [(match_id, placed(players, ranks)), (match_id, placed(players, ranks))]
        rng.shuffle(jobs)
        results = await asyncio.gather(
            *(store.apply_match_result(m, "poker", p) for m, p in jobs), return_exceptions=True
        )
        rows = await pool.fetch("SELECT rating, games_played FROM ratings")
        rated = await pool.fetchval("SELECT count(*) FROM rated_matches")
        return results, rows, rated, placements_total

    results, rows, rated, placements_total = run(database_url, scenario)

    errors = [r for r in results if isinstance(r, BaseException)]
    assert errors == []
    assert sum(r is not None for r in results) == 60
    assert rated == 60
    # Zero-sum: every point won was lost by someone, so the ratings still average 1000.
    assert sum(row["rating"] - 1000 for row in rows) == pytest.approx(0, abs=1e-6)
    assert sum(row["games_played"] for row in rows) == placements_total
