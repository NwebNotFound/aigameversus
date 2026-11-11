"""What a spectator does with a match through the API: pause, resume, speed, abort, board, cost."""

import asyncio
import time
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from arena.api.app import app
from arena.db.database import connect, migrate
from arena.db.match_store import MatchStore
from arena.engine.replay import replay
from arena.engine.types import Placement
from games.liars_deck.plugin import LiarsDeck
from tests.db.test_matches_api import as_events, follow, start


@pytest.fixture
def client(database_url, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", database_url)
    with TestClient(app) as client:
        yield client


def first_event(client, match_id):
    with client.websocket_connect(f"/matches/{match_id}/events") as stream:
        return stream.receive_json()


def log_length(client, match_id):
    return len(client.get(f"/matches/{match_id}/events").json())


def test_paused_match_stops_between_turns_and_resumes_where_it_stopped(client):
    match = start(client, seed=3, turn_delay=0.05)

    paused = client.post(f"/matches/{match['id']}/pause")
    time.sleep(0.5)  # at most the turn that was being played when the pause came is stored
    stopped_at = log_length(client, match["id"])
    time.sleep(0.5)

    assert paused.json() == {"paused": True, "turn_delay": 0.05}
    assert log_length(client, match["id"]) == stopped_at
    assert client.get(f"/matches/{match['id']}").json()["status"] == "running"
    assert client.get(f"/matches/{match['id']}/control").json()["paused"] is True

    resumed = client.post(f"/matches/{match['id']}/resume")
    log, close_code = follow(client, match["id"])

    assert resumed.json() == {"paused": False, "turn_delay": 0.05}
    assert (log[-1]["type"], close_code) == ("match_finished", 1000)
    assert stopped_at < len(log)
    assert client.get(f"/matches/{match['id']}").json()["status"] == "finished"
    # The pause changed nothing in the game: the same seed without a pause gives the same log.
    unpaused, _ = follow(client, start(client, seed=3)["id"])
    assert [(e["type"], e["data"]) for e in log] == [(e["type"], e["data"]) for e in unpaused]


def test_a_faster_speed_also_cuts_the_wait_that_has_begun(client):
    match = start(client, turn_delay=30)
    first_event(client, match["id"])

    began = time.monotonic()
    changed = client.put(f"/matches/{match['id']}/speed", json={"turn_delay": 0})
    log, _ = follow(client, match["id"])

    assert changed.json() == {"paused": False, "turn_delay": 0}
    assert log[-1]["type"] == "match_finished"
    assert time.monotonic() - began < 10


def test_aborted_match_stops_for_good_and_keeps_its_log(client):
    match = start(client, turn_delay=30)
    first = first_event(client, match["id"])

    aborted = client.post(f"/matches/{match['id']}/abort")
    log, close_code = follow(client, match["id"])

    assert aborted.status_code == 200
    record = aborted.json()
    assert record["status"] == "aborted"
    assert record["finished_at"] is not None and record["placements"] is None
    assert client.get(f"/matches/{match['id']}").json() == record
    assert (log[0], close_code) == (first, 1000)
    assert "match_finished" not in [event["type"] for event in log]
    assert client.get("/matches", params={"status": "aborted"}).json()[0]["id"] == match["id"]


def test_paused_match_can_be_aborted(client):
    match = start(client, turn_delay=30)
    client.post(f"/matches/{match['id']}/pause")

    assert client.post(f"/matches/{match['id']}/abort").json()["status"] == "aborted"


def test_match_that_is_not_running_cannot_be_controlled(client):
    match = start(client)
    follow(client, match["id"])  # until it has finished
    url = f"/matches/{match['id']}"

    for response in (
        client.get(f"{url}/control"),
        client.post(f"{url}/pause"),
        client.post(f"{url}/resume"),
        client.put(f"{url}/speed", json={"turn_delay": 1}),
        client.post(f"{url}/abort"),
    ):
        assert response.status_code == 409, response.request.url
        assert response.json()["detail"] == "The match is not running, so it cannot be controlled."
    assert client.get(url).json()["status"] == "finished"


def test_unknown_match_cannot_be_controlled_or_shown(client):
    url = f"/matches/{uuid4()}"

    for response in (
        client.get(f"{url}/control"),
        client.post(f"{url}/pause"),
        client.post(f"{url}/resume"),
        client.put(f"{url}/speed", json={"turn_delay": 1}),
        client.post(f"{url}/abort"),
        client.get(f"{url}/board"),
        client.get(f"{url}/cost"),
    ):
        assert response.status_code == 404, response.request.url


@pytest.mark.parametrize("turn_delay", [-1, 61, "fast"])
def test_speed_out_of_range_is_refused(client, turn_delay):
    match = start(client, turn_delay=30)

    response = client.put(f"/matches/{match['id']}/speed", json={"turn_delay": turn_delay})

    assert response.status_code == 422
    assert client.get(f"/matches/{match['id']}/control").json()["turn_delay"] == 30


def test_board_is_what_the_game_draws_after_the_stored_log(client):
    match = start(client, game="liars_deck", seed=5)
    log, _ = follow(client, match["id"])

    board = client.get(f"/matches/{match['id']}/board").json()

    plugin = LiarsDeck()
    expected = plugin.render_spec(replay(plugin, as_events(log)))
    assert board == {"game": "liars_deck", "events": len(log), "spec": expected}
    assert board["spec"]["layout"] == "card_table"


def test_board_of_a_running_match_shows_its_completed_turns(client):
    match = start(client, game="liars_deck", seed=5, turn_delay=30)
    first_event(client, match["id"])

    board = client.get(f"/matches/{match['id']}/board").json()
    stored = client.get(f"/matches/{match['id']}/events").json()

    plugin = LiarsDeck()
    assert board["events"] == len(stored) > 0
    assert board["spec"] == plugin.render_spec(replay(plugin, as_events(stored)))


def test_game_without_a_board_says_so(client):
    match = start(client, game="toy")
    log, _ = follow(client, match["id"])

    assert client.get(f"/matches/{match['id']}/board").json() == {
        "game": "toy",
        "events": len(log),
        "spec": None,
    }


def book(database_url, calls):
    async def run():
        pool = await connect(database_url)
        try:
            for match_id, player, cost in calls:
                await pool.execute(
                    "INSERT INTO model_calls (match_id, player, model, called_at, cost_micro_eur) "
                    "VALUES ($1, $2, 'mock', $3, $4)",
                    match_id,
                    player,
                    datetime.now(UTC),
                    cost,
                )
        finally:
            await pool.close()

    asyncio.run(run())


def test_cost_sums_the_ledger_of_the_match_per_player(client, database_url):
    match = start(client, turn_delay=30)
    other = start(client, turn_delay=30)
    book(
        database_url,
        [
            (match["id"], "p1", 120),
            (match["id"], "p2", 50),
            (match["id"], "p1", 180),
            (other["id"], "p1", 9_000),
        ],
    )

    assert client.get(f"/matches/{match['id']}/cost").json() == {
        "total_micro_eur": 350,
        "players": {"p1": 300, "p2": 50},
    }


def test_match_of_bots_costs_nothing(client):
    match = start(client)

    assert client.get(f"/matches/{match['id']}/cost").json() == {
        "total_micro_eur": 0,
        "players": {},
    }


def stored_types(client, match_id):
    return [event["type"] for event in client.get(f"/matches/{match_id}/events").json()]


def wait_for(condition, timeout=10.0):
    deadline = time.monotonic() + timeout
    while not condition():
        if time.monotonic() > deadline:
            pytest.fail("condition not reached in time")
        time.sleep(0.02)


def test_match_that_has_ended_cannot_be_aborted_while_its_record_is_closed(client, monkeypatch):
    close = MatchStore.close

    async def slow_close(self, match_id, status, placements=None):
        if status == "finished":
            await asyncio.sleep(0.5)  # an abort arrives between the last event and the record
        await close(self, match_id, status, placements)

    monkeypatch.setattr(MatchStore, "close", slow_close)
    match = start(client)
    wait_for(lambda: stored_types(client, match["id"])[-1:] == ["match_finished"])

    aborted = client.post(f"/matches/{match['id']}/abort")
    follow(client, match["id"])  # until the record is closed

    assert aborted.status_code == 409
    assert aborted.json()["detail"] == "The match has ended, so it cannot be aborted."
    record = client.get(f"/matches/{match['id']}").json()
    assert record["status"] == "finished"
    assert record["placements"] is not None


def test_match_paused_just_before_its_end_still_ends(client):
    full = stored_types(client, follow_to_end(client, start(client, seed=3)))
    assert full[-1] == "match_finished"
    match = start(client, seed=3, turn_delay=1)
    # Everything but the end is stored: the match waits its delay before the last turn.
    wait_for(lambda: len(stored_types(client, match["id"])) == len(full) - 1)

    client.post(f"/matches/{match['id']}/pause")
    wait_for(lambda: client.get(f"/matches/{match['id']}").json()["status"] != "running", 5)
    log, _ = follow(client, match["id"])

    assert [event["type"] for event in log] == full
    assert client.get(f"/matches/{match['id']}").json()["status"] == "finished"


def follow_to_end(client, match):
    follow(client, match["id"])
    return match["id"]


def test_a_record_that_is_closed_is_never_closed_again(database_url):
    match_id = uuid4()

    async def run():
        pool = await connect(database_url)
        try:
            await migrate(pool)
            store = MatchStore(pool)
            await store.create(match_id, "toy", ["p1", "p2"], 1, {})
            await store.close(match_id, "finished", [Placement(player="p1", rank=1)])
            await store.close(match_id, "aborted")
            return await store.get(match_id)
        finally:
            await pool.close()

    record = asyncio.run(run())

    assert record.status == "finished"
    assert record.placements == [Placement(player="p1", rank=1)]
