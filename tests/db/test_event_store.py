import asyncio
from functools import partial
from uuid import uuid4

import asyncpg
import pytest
from fastapi.testclient import TestClient

from arena.agents.mock_llm import MockLLM
from arena.agents.model import ModelReply, ToolCall
from arena.agents.random_bot import random_bots
from arena.agents.runner import ModelAgent
from arena.api.app import app
from arena.db.database import connect, migrate
from arena.db.event_store import EventStore
from arena.engine.match import Match
from arena.engine.replay import replay
from arena.engine.types import Event, EventSource
from games.toy.plugin import ToyGame

PLAYERS = ["p1", "p2", "p3"]


def with_store(database_url, scenario):
    """Run `scenario(store)` against a migrated, empty database."""

    async def run():
        pool = await connect(database_url)
        try:
            await migrate(pool)
            return await scenario(EventStore(pool))
        finally:
            await pool.close()

    return asyncio.run(run())


def game_event(type, data=None, visible_to=None):
    return Event(source=EventSource.GAME, type=type, data=data or {}, visible_to=visible_to)


def test_stored_match_replays_to_the_exact_end_state(database_url):
    plugin = ToyGame()
    match_id = uuid4()

    async def scenario(store):
        match = Match(
            plugin,
            random_bots(plugin, PLAYERS, 21),
            seed=21,
            sink=partial(store.append, match_id),
        )
        await match.run()
        return match, await store.load(match_id)

    match, stored = with_store(database_url, scenario)

    assert stored == match.events
    assert replay(plugin, stored) == match.state


def test_match_of_model_players_is_stored_whatever_they_write(database_url):
    plugin = ToyGame()
    match_id = uuid4()

    def odd_model(messages, tools):
        # Postgres refuses NUL, half surrogate pairs and NaN; the engine removes them.
        return ModelReply(
            text="my plan\x00 \ud83d ♠ <b>",
            tool_calls=(ToolCall("play\x00_card", '{"card": NaN, "why": "\\u0000\\ud83d"}'),),
        )

    async def scenario(store):
        agents = {player: ModelAgent(MockLLM(odd_model), plugin) for player in PLAYERS}
        match = Match(plugin, agents, seed=21, sink=partial(store.append, match_id))
        await match.run()
        return match, await store.load(match_id)

    match, stored = with_store(database_url, scenario)

    assert stored == match.events
    assert replay(plugin, stored) == match.state
    thought = next(event for event in stored if event.type == "thought")
    assert thought.data["text"] == "my plan  ♠ <b>"
    assert thought.visible_to == ()
    rejected = next(event for event in stored if event.type == "action_rejected")
    assert rejected.data["arguments"] == {"card": None, "why": ""}


def test_visibility_and_nested_data_survive_storage(database_url):
    events = [
        game_event("public", {"cards": [3, 1, 2], "by": {"p1": {"won": True, "score": 1.5}}}),
        game_event("private", {"text": 'Über\'n "Tisch" \\ ♠'}, visible_to=("p2", "p1")),
        game_event("spectators_only", {"nothing": None}, visible_to=()),
    ]
    match_id = uuid4()

    async def scenario(store):
        await store.append(match_id, 0, events)
        return await store.load(match_id)

    assert with_store(database_url, scenario) == events


def test_logs_of_different_matches_do_not_mix(database_url):
    first, second = uuid4(), uuid4()

    async def scenario(store):
        await store.append(first, 0, [game_event("a"), game_event("b")])
        await store.append(second, 0, [game_event("c")])
        await store.append(first, 2, [game_event("d")])
        return await store.load(first), await store.load(second), await store.load(uuid4())

    in_first, in_second, in_unknown = with_store(database_url, scenario)

    assert [event.type for event in in_first] == ["a", "b", "d"]
    assert [event.type for event in in_second] == ["c"]
    assert in_unknown == []


def test_second_writer_on_a_taken_position_is_refused_and_writes_nothing(database_url):
    match_id = uuid4()

    async def scenario(store):
        await store.append(match_id, 0, [game_event("a"), game_event("b")])
        with pytest.raises(asyncpg.UniqueViolationError):
            await store.append(match_id, 1, [game_event("clash"), game_event("after")])
        return await store.load(match_id)

    assert [event.type for event in with_store(database_url, scenario)] == ["a", "b"]


def test_migrating_twice_applies_nothing_new(database_url):
    async def run():
        pool = await connect(database_url)
        try:
            return await migrate(pool), await migrate(pool)
        finally:
            await pool.close()

    first, second = asyncio.run(run())

    assert first == ["0001_match_events.sql", "0002_model_calls.sql"]
    assert second == []


def test_server_start_creates_the_schema(database_url, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", database_url)

    with TestClient(app) as client:
        assert client.get("/health").json() == {"status": "ok"}

    async def run():
        pool = await connect(database_url)
        try:
            return await migrate(pool), await EventStore(pool).load(uuid4())
        finally:
            await pool.close()

    # Nothing left to migrate, and the event table can be read.
    assert asyncio.run(run()) == ([], [])
