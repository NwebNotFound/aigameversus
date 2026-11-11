"""Relationships in Postgres: trust and notes per pair, from the facts of each match."""

import asyncio
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from arena.api.app import app
from arena.db.database import connect, migrate
from arena.engine.types import Event, EventSource
from arena.memory.facts import match_facts
from arena.memory.store import MemoryStore
from arena.memory.trust import load_rules, match_changes
from arena.ratings.store import RatingStore
from tests.db.test_matches_api import as_events, follow, start


def game(type_, data, visible_to=None):
    return Event(source=EventSource.GAME, type=type_, data=data, visible_to=visible_to)


def votes(day, voter, target, times=1):
    return [game("day_started", {"day": day, "order": []})] + [
        game("vote_cast", {"player": voter, "target": target}) for _ in range(times)
    ]


def run(database_url, scenario):
    async def go():
        pool = await connect(database_url)
        try:
            await migrate(pool)
            ratings = RatingStore(pool)
            ann = await ratings.create_profile("Ann", "mock-llm")
            bob = await ratings.create_profile("Bob", "mock-llm")
            return await scenario(MemoryStore(pool), {"a": ann, "b": bob}, pool)
        finally:
            await pool.close()

    return asyncio.run(go())


def test_a_match_counts_once(database_url):
    async def scenario(store, seats, pool):
        match_id = uuid4()
        first = await store.remember_match(match_id, "werewolf", votes(1, "b", "a"), seats)
        again = await store.remember_match(match_id, "werewolf", votes(1, "b", "a"), seats)
        return (
            first,
            again,
            await store.relationships(seats["a"]),
            await store.relationships(seats["b"]),
        )

    first, again, of_ann, of_bob = run(database_url, scenario)

    vote = load_rules().facts["werewolf"]["voted_against_me"].trust
    assert (first, again) == (True, False)
    assert [(r.name, r.trust) for r in of_ann] == [("Bob", vote)]
    assert [n.text for n in of_ann[0].notes] == ["voted against me on day 1"]
    assert of_bob == []  # Bob saw nothing about Ann


def test_trust_is_clamped_and_notes_are_capped_newest_first(database_url):
    rules = load_rules()

    async def scenario(store, seats, pool):
        for day in range(1, 31):
            await store.remember_match(uuid4(), "werewolf", votes(day, "b", "a", times=2), seats)
        return await store.relationships(seats["a"])

    (bob,) = run(database_url, scenario)

    assert bob.trust == rules.limits.min
    assert len(bob.notes) == rules.limits.notes
    assert bob.notes[0].text == "voted against me on day 30"
    assert bob.notes[-1].text == f"voted against me on day {31 - rules.limits.notes // 2}"


def test_strongest_feelings_come_first(database_url):
    async def scenario(store, seats, pool):
        cara = await RatingStore(pool).create_profile("Cara", "mock-llm")
        three = {**seats, "c": cara}
        log = [
            game("pack_revealed", {"wolves": ["a", "c"]}, ["a", "c"]),
            *votes(1, "b", "a"),
        ]
        await store.remember_match(uuid4(), "werewolf", log, three)
        return await store.relationships(seats["a"])

    relations = run(database_url, scenario)

    rules = load_rules().facts["werewolf"]
    assert [(r.name, r.trust) for r in relations] == [
        ("Cara", rules["packmate"].trust),
        ("Bob", rules["voted_against_me"].trust),
    ]


@pytest.fixture
def client(database_url, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", database_url)
    with TestClient(app) as client:
        yield client


def test_a_bot_match_through_the_api_fills_the_relations_of_its_bots(client):
    match = start(client, game="werewolf", players=8, seed=4)
    log, _ = follow(client, match["id"])
    params = {"game": "werewolf", "kind": "all", "group_bots": False}
    rows = client.get("/leaderboard", params=params).json()["rows"]
    bots = {row["name"].removeprefix("Random Bot "): row["profile_id"] for row in rows}

    relations = client.get(f"/profiles/{bots['p1']}/relations").json()

    changes = match_changes(
        "werewolf", match_facts("werewolf", as_events(log), list(bots)), load_rules()
    )
    expected = {
        bots[about]: change.trust
        for (observer, about), change in changes.items()
        if observer == "p1"
    }
    got = {r["profile_id"]: r["trust"] for r in relations["relations"]}
    assert got == {other: trust for other, trust in expected.items()}
    assert all(
        r["notes"] and r["notes"][0]["match_id"] == match["id"] for r in relations["relations"]
    )


def test_unknown_profile_has_no_relations(client):
    assert client.get(f"/profiles/{UUID(int=0)}/relations").status_code == 404
