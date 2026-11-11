"""Long-term memory in Postgres: match summaries, the memory block, memory off and reset."""

import asyncio
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

import pytest
from fastapi.testclient import TestClient

from arena.agents.mock_llm import MockLLM, tool_call
from arena.agents.runner import ModelAgent
from arena.api.app import app
from arena.cli import main
from arena.db.database import connect, migrate
from arena.engine.match import Match
from arena.engine.types import Event, EventSource
from arena.memory.block import MEMORY_CHARS, memory_block
from arena.memory.store import MemoryStore
from arena.ratings.store import BOT_MODEL_ID, RatingStore
from games.toy.plugin import ToyGame
from tests.db.test_matches_api import follow, start


def game(type_, data, visible_to=None):
    return Event(source=EventSource.GAME, type=type_, data=data, visible_to=visible_to)


def finished(*placements):
    return Event(
        source=EventSource.ENGINE,
        type="match_finished",
        data={"placements": [{"player": p, "rank": r} for p, r in placements]},
        visible_to=None,
    )


def werewolf_day(day, *votes, placements=(("a", 1), ("b", 2), ("c", 2))):
    return [
        game("day_started", {"day": day, "order": []}),
        *[game("vote_cast", {"player": voter, "target": target}) for voter, target in votes],
        finished(*placements),
    ]


def run(database_url, scenario):
    """`scenario(store, profiles, pool)` with three profiles Ann, Bob and Cara on seats a, b, c."""

    async def go():
        pool = await connect(database_url)
        try:
            await migrate(pool)
            ratings = RatingStore(pool)
            profiles = {
                seat: await ratings.create_profile(name, "mock-llm")
                for seat, name in (("a", "Ann"), ("b", "Bob"), ("c", "Cara"))
            }
            return await scenario(MemoryStore(pool), profiles, pool)
        finally:
            await pool.close()

    return asyncio.run(go())


def test_every_seated_player_gets_a_summary_of_its_own_view(database_url):
    async def scenario(store, seats, pool):
        log = werewolf_day(1, ("b", "a"), ("c", "b"))
        await store.remember_match(uuid4(), "werewolf", log, seats, game_name="Werewolf")
        return {seat: await store.memories(profile) for seat, profile in seats.items()}

    memories = run(database_url, scenario)

    assert [m.summary for m in memories["a"]] == [
        "Werewolf against Bob, Cara: I finished 1st of 3. Bob voted against me on day 1."
    ]
    assert [m.summary for m in memories["b"]] == [
        "Werewolf against Ann, Cara: I finished 2nd of 3. Cara voted against me on day 1."
    ]
    assert [m.summary for m in memories["c"]] == ["Werewolf against Ann, Bob: I finished 2nd of 3."]


def test_the_block_is_about_the_seated_opponents_only(database_url):
    async def scenario(store, seats, pool):
        log = werewolf_day(1, ("b", "a"), ("c", "a"))
        await store.remember_match(uuid4(), "werewolf", log, seats, game_name="Werewolf")
        # This match: Ann meets only Bob, now on seat p3.
        return await memory_block(store, seats["a"], {"p1": seats["a"], "p3": seats["b"]})

    block = run(database_url, scenario)

    assert block.splitlines()[0] == (
        "- p3 (you know them as Bob): trust -6. voted against me on day 1."
    )
    # Cara is not at this table: no line about her, though Ann remembers her too.
    assert [line for line in block.splitlines() if "you know them as" in line] == [
        block.splitlines()[0]
    ]
    assert "Earlier matches against them, newest first:" in block
    assert len(block) <= MEMORY_CHARS


def test_a_block_never_holds_what_another_player_remembers(database_url):
    async def scenario(store, seats, pool):
        # Bob saw Ann vote against him; Ann saw nothing about Bob.
        log = werewolf_day(1, ("a", "b"))
        await store.remember_match(uuid4(), "werewolf", log, seats, game_name="Werewolf")
        ann = await memory_block(store, seats["a"], {"b": seats["b"]})
        bob = await memory_block(store, seats["b"], {"a": seats["a"]})
        return ann, bob

    ann, bob = run(database_url, scenario)

    assert "voted against me" in bob
    assert "voted against me" not in ann
    assert "trust" not in ann  # Ann has no feeling about Bob, only her match summary


def test_nobody_known_means_no_block(database_url):
    async def scenario(store, seats, pool):
        return await memory_block(store, seats["a"], {"b": seats["b"], "c": seats["c"]})

    assert run(database_url, scenario) is None


def test_the_block_keeps_its_length_cap_and_its_order(database_url):
    async def scenario(store, seats, pool):
        for day in range(1, 41):
            log = werewolf_day(day, ("b", "a"), ("b", "a"), ("c", "a"))
            await store.remember_match(uuid4(), "werewolf", log, seats, game_name="Werewolf")
        return await memory_block(store, seats["a"], {"b": seats["b"], "c": seats["c"]})

    block = run(database_url, scenario)

    lines = block.splitlines()
    assert len(block) <= MEMORY_CHARS
    # Bob voted twice a day: the stronger feeling comes first, newest notes first.
    assert lines[0].startswith("- b (you know them as Bob): trust -100. voted against me on day 40")
    assert lines[1].startswith("- c (you know them as Cara): trust -100.")
    assert all(not line.endswith(("; ", ",")) for line in lines)


def test_reset_forgets_one_player_or_everyone_and_old_matches_stay_counted(database_url):
    async def scenario(store, seats, pool):
        match_id = uuid4()
        log = werewolf_day(1, ("b", "a"), ("a", "b"))
        await store.remember_match(match_id, "werewolf", log, seats, game_name="Werewolf")
        only_ann = await store.reset(seats["a"])
        bob_left = (await store.relationships(seats["b"]), await store.memories(seats["b"]))
        everyone = await store.reset()
        again = await store.remember_match(match_id, "werewolf", log, seats)
        return only_ann, bob_left, everyone, again, await store.memories(seats["b"])

    only_ann, (bob_relations, bob_memories), everyone, again, after = run(database_url, scenario)

    assert (only_ann.relationships, only_ann.memories) == (1, 1)
    assert len(bob_relations) == 1 and len(bob_memories) == 1
    assert (everyone.relationships, everyone.memories) == (1, 2)
    assert again is False and after == []


def test_a_model_sees_its_memory_in_every_prompt(database_url):
    async def scenario(store, seats, pool):
        await store.remember_match(
            uuid4(), "werewolf", werewolf_day(1, ("b", "a")), seats, game_name="Werewolf"
        )
        block = await memory_block(store, seats["a"], {"p2": seats["b"]})
        plugin = ToyGame()
        mock = MockLLM(*[tool_call("play_card", {"card": card}) for card in range(1, 11)])
        agents = {
            "p1": ModelAgent(mock, plugin, memory=block),
            "p2": ModelAgent(
                MockLLM(*[tool_call("play_card", {"card": c}) for c in range(1, 11)]), plugin
            ),
        }
        await Match(plugin, agents, seed=3).run()
        return block, mock.calls

    block, calls = run(database_url, scenario)

    assert calls
    for messages, _ in calls:
        assert f"<memory>\n{block}\n</memory>" in messages[1]["content"]


@pytest.fixture
def client(database_url, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", database_url)
    with TestClient(app) as client:
        yield client


def bots(client, game_id, seats=8):
    """The profile of the random bot on each seat (the store derives them from the seat)."""
    return {
        f"p{n}": str(uuid5(NAMESPACE_URL, f"aigameversus/bot/{BOT_MODEL_ID}/p{n}"))
        for n in range(1, seats + 1)
    }


def test_a_match_with_memory_off_remembers_nothing(client):
    match = start(client, game="werewolf", players=8, seed=4, memory=False)
    follow(client, match["id"])

    p1 = bots(client, "werewolf")["p1"]
    assert match["memory"] is False
    assert client.get(f"/matches/{match['id']}").json()["memory"] is False
    assert client.get(f"/profiles/{p1}/relations").json()["relations"] == []
    assert client.get(f"/profiles/{p1}/memories").json() == []


def test_a_match_with_memory_is_remembered_and_can_be_forgotten(client):
    match = start(client, game="werewolf", players=8, seed=4)
    follow(client, match["id"])
    p1 = bots(client, "werewolf")["p1"]

    memories = client.get(f"/profiles/{p1}/memories").json()
    assert [m["match_id"] for m in memories] == [match["id"]]
    assert memories[0]["summary"].startswith("Werewolf against Random Bot p2")

    reset = client.post("/memory/reset", json={"profile_id": p1}).json()
    assert reset["memories"] == 1
    assert client.get(f"/profiles/{p1}/memories").json() == []
    refused = client.post("/memory/reset", json={})
    assert refused.status_code == 422
    assert "confirm" in refused.json()["detail"]
    p2 = bots(client, "werewolf")["p2"]
    assert len(client.get(f"/profiles/{p2}/memories").json()) == 1  # nothing was forgotten
    everyone = client.post("/memory/reset", json={"confirm": True}).json()
    assert everyone["memories"] == 7  # the other seven bots
    assert client.get(f"/profiles/{p2}/memories").json() == []


def test_unknown_profile_has_no_memories(client):
    assert client.get(f"/profiles/{UUID(int=0)}/memories").status_code == 404


def test_the_cli_resets_memory(database_url, monkeypatch, capsys):
    monkeypatch.setenv("DATABASE_URL", database_url)

    async def remember():
        pool = await connect(database_url)
        try:
            await migrate(pool)
            ratings = RatingStore(pool)
            seats = {s: await ratings.create_profile(s, "mock-llm") for s in ("a", "b")}
            await MemoryStore(pool).remember_match(
                uuid4(),
                "werewolf",
                werewolf_day(1, ("b", "a"), placements=(("a", 1), ("b", 2))),
                seats,
            )
            return seats
        finally:
            await pool.close()

    seats = asyncio.run(remember())

    assert main(["memory", "reset", "--profile", str(seats["a"]), "--yes"]) == 0
    assert capsys.readouterr().out.strip() == (
        f"Forgot 1 relationships and 1 match memories of profile {seats['a']}."
    )
    assert main(["memory", "reset", "--yes"]) == 0
    assert "Forgot 0 relationships and 1 match memories of every player." in capsys.readouterr().out
