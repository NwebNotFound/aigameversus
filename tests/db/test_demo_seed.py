import asyncio

import pytest

from arena.db.database import connect, migrate
from arena.ratings.demo_seed import DEMO_NAMES, GAME_ID, RefusedError, seed_demo
from arena.ratings.store import RatingStore


def run(database_url, scenario):
    async def go():
        pool = await connect(database_url)
        try:
            await migrate(pool)
            return await scenario(pool)
        finally:
            await pool.close()

    return asyncio.run(go())


def test_seed_fills_the_board_with_demo_profiles_only(database_url):
    async def scenario(pool):
        applied = await seed_demo(pool, matches=12, seed=3)
        return applied, await RatingStore(pool).leaderboard(GAME_ID, demo=True)

    applied, board = run(database_url, scenario)

    assert applied == 12
    assert {s.name for s in board} <= set(DEMO_NAMES)
    assert all(s.name.startswith("DEMO ") and s.model_id == "random-bot" for s in board)
    assert sum(s.games_played for s in board) >= 12 * 2


def test_demo_profiles_are_marked_and_the_board_hides_them_by_default(database_url):
    async def scenario(pool):
        await seed_demo(pool, matches=6, seed=3)
        store = RatingStore(pool)
        marked = await pool.fetchval("SELECT count(*) FROM player_profiles WHERE is_demo")
        return marked, await store.leaderboard(GAME_ID), await store.demo_profiles()

    marked, hidden, count = run(database_url, scenario)

    assert marked == len(DEMO_NAMES)
    assert hidden == []
    assert count > 0


def test_seeding_again_with_the_same_seed_adds_nothing(database_url):
    async def scenario(pool):
        first = await seed_demo(pool, matches=5, seed=7)
        second = await seed_demo(pool, matches=5, seed=7)
        profiles = await pool.fetchval("SELECT count(*) FROM player_profiles")
        return first, second, profiles

    assert run(database_url, scenario) == (5, 0, len(DEMO_NAMES))


def test_same_seed_gives_the_same_board(database_url):
    async def board(pool):
        await seed_demo(pool, matches=8, seed=11)
        standings = await RatingStore(pool).leaderboard(GAME_ID, demo=True)
        return [(s.name, round(s.rating, 6), s.games_played) for s in standings]

    async def scenario(pool):
        first = await board(pool)
        await pool.execute("TRUNCATE player_profiles, ratings, rated_matches CASCADE")
        return first, await board(pool)

    first, second = run(database_url, scenario)

    assert first and first == second


def test_refuses_when_real_profiles_exist(database_url):
    async def scenario(pool):
        await RatingStore(pool).create_profile("Claude 7", "anthropic/claude")
        with pytest.raises(RefusedError, match="not demo data"):
            await seed_demo(pool, matches=3)
        return await pool.fetchval("SELECT count(*) FROM rated_matches")

    assert run(database_url, scenario) == 0
