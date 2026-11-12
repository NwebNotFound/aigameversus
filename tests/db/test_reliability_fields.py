"""The refused-answer share, the cut-off warning and last_seen, read from stored decision events."""

import asyncio
from datetime import UTC, datetime
from uuid import uuid4

from arena.config import ReliabilityRules
from arena.db.database import connect, migrate
from arena.db.reliability import reliabilities

RULES = ReliabilityRules()
WHEN = datetime(2026, 11, 12, 9, 30, tzinfo=UTC)


async def play(pool, model, moves, started=WHEN, seats_of_model=("p1",)):
    """A finished match in which `model` sat in these seats, each making these decision events."""
    match_id = uuid4()
    seats = {p: {"model_id": model, "kind": "model", "name": model} for p in seats_of_model}
    await pool.execute(
        "INSERT INTO matches (id, game, status, players, seed, settings, started_at, seats) "
        "VALUES ($1, 'toy', 'finished', $2, 1, '{}', $3, $4)",
        match_id,
        list(seats_of_model),
        started,
        seats,
    )
    moves_of_all = [(p, data) for p in seats_of_model for data in moves]
    for seq, (player, data) in enumerate(moves_of_all):
        await pool.execute(
            "INSERT INTO match_events (match_id, seq, source, type, data, visible_to, recorded_at) "
            "VALUES ($1, $2, 'engine', 'decision', $3, '{}', $4)",
            match_id,
            seq,
            {"player": player, "fallback": None, **data},
            started,
        )


def run(database_url, plan):
    async def go():
        pool = await connect(database_url)
        try:
            await migrate(pool)
            await plan(pool)
            return await reliabilities(pool, ["acme/x", "acme/old", "acme/new"], RULES)
        finally:
            await pool.close()

    return asyncio.run(go())


def test_twelve_of_thirteen_refused_answers_cut_off_is_warned_and_dated(database_url):
    told = {"cutoffs": 0, "rate_limits": 0}

    async def plan(pool):
        cut = [dict(answers=2, **told | {"cutoffs": 1}) for _ in range(12)]
        await play(pool, "acme/x", cut + [dict(answers=2, **told)] + [dict(answers=1, **told)] * 7)

    found = run(database_url, plan)["acme/x"]

    assert found.status == "ok"
    assert (found.answers, found.rejected, found.rejected_cut_off) == (33, 13, 12)
    assert found.rejected_rate == 13 / 33 and found.last_seen == WHEN
    assert any("12 of 13 refused answers ran into the output limit" in w for w in found.warnings)


def test_a_model_from_before_the_counters_has_no_cut_off_number_but_a_refusal_share(database_url):
    async def plan(pool):
        await play(pool, "acme/old", [dict(answers=2)] * 10 + [dict(answers=1)] * 10)

    found = run(database_url, plan)["acme/old"]

    assert (found.rejected, found.rejected_rate) == (10, 10 / 30)
    assert found.rejected_cut_off is None and found.rejected_told == 0
    assert not any("refused answers" in w for w in found.warnings)


def test_a_model_never_seated_has_nothing_to_show(database_url):
    found = run(database_url, lambda pool: asyncio.sleep(0))["acme/new"]

    assert found.status == "unknown" and found.last_seen is None
    assert (found.answers, found.rejected_rate, found.rejected_cut_off) == (0, None, None)


def test_last_seen_is_the_newest_match_of_the_model(database_url):
    later = datetime(2026, 11, 13, 8, 0, tzinfo=UTC)

    async def plan(pool):
        await play(pool, "acme/x", [dict(answers=1)] * 3, started=WHEN)
        await play(pool, "acme/x", [dict(answers=1)] * 3, started=later)

    assert run(database_url, plan)["acme/x"].last_seen == later


def test_a_model_in_two_seats_counts_the_answers_of_both_and_the_match_once(database_url):
    told = {"cutoffs": 0, "rate_limits": 0}

    async def plan(pool):
        await play(pool, "acme/x", [dict(answers=2, **told)] * 10, seats_of_model=("p1", "p2"))

    found = run(database_url, plan)["acme/x"]

    assert (found.matches, found.answers, found.rejected) == (1, 40, 20)
    assert found.rejected_rate == 0.5 and found.last_seen == WHEN
