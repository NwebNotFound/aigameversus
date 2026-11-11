"""Matches through the API: start one, read its record, follow its events over WebSocket."""

import asyncio
import os
from datetime import datetime
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from arena.agents.random_bot import random_bots
from arena.api import live
from arena.api.app import app
from arena.db.database import connect, migrate
from arena.db.match_store import MatchStore
from arena.engine.match import Match
from arena.engine.replay import replay
from arena.engine.types import Event, Placement
from arena.ratings.store import RatingStore
from games.toy.plugin import ToyGame

NEVER_ENDS = """
from tests.engine.counter_game import SequentialCounter


class Plugin(SequentialCounter):
    id = "broken"

    def step(self, state, ctx):
        pass  # never closes a round: after both players moved, a turn passes without an event
"""


NEVER_OVER = """
from tests.engine.counter_game import SequentialCounter


class Plugin(SequentialCounter):
    id = "endless"
    max_turns = 40

    def is_over(self, state):
        return False  # round after round, each with progress, and no end
"""


@pytest.fixture
def client(database_url, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", database_url)
    with TestClient(app) as client:
        yield client


def start(client, **body):
    response = client.post("/matches", json={"game": "toy", **body})
    assert response.status_code == 201, response.text
    return response.json()


def follow(client, match_id, *, at_most=None):
    """Everything the event stream of a match sends until the server closes it.

    With `at_most`, a match that sends more events fails the test instead of running on.
    """
    received = []
    with client.websocket_connect(f"/matches/{match_id}/events") as stream:
        try:
            while True:
                received.append(stream.receive_json())
                if at_most is not None and len(received) > at_most:
                    pytest.fail("match did not stop at its turn limit")
        except WebSocketDisconnect as closed:
            return received, closed.code


def as_events(messages):
    return [Event(**{name: value for name, value in m.items() if name != "seq"}) for m in messages]


def test_games_are_listed(client):
    games = client.get("/games").json()

    assert {"id": "toy", "name": "High Card", "min_players": 2, "max_players": 4} in games


def test_started_match_streams_its_whole_log_and_ends_finished(client):
    match = start(client, players=3, seed=11)

    stream, close_code = follow(client, match["id"])

    assert match["game"] == "toy"
    assert match["status"] == "running"
    assert (match["players"], match["seed"]) == (["p1", "p2", "p3"], 11)
    assert (match["finished_at"], match["placements"]) == (None, None)
    # The stream is the log from its first to its last event, and then the server closes it.
    assert close_code == 1000
    assert [message["seq"] for message in stream] == list(range(len(stream)))
    assert (stream[0]["type"], stream[-1]["type"]) == ("match_started", "match_finished")
    assert stream == client.get(f"/matches/{match['id']}/events").json()
    # A spectator gets everything, also what only one player may see.
    assert [m["visible_to"] for m in stream if m["type"] == "hand_dealt"] == [
        ["p1"],
        ["p2"],
        ["p3"],
    ]
    record = client.get(f"/matches/{match['id']}").json()
    assert record["status"] == "finished"
    assert record["placements"] == stream[-1]["data"]["placements"]
    assert datetime.fromisoformat(record["finished_at"]) >= datetime.fromisoformat(
        record["started_at"]
    )
    assert record | {"status": "running", "finished_at": None, "placements": None} == match


def test_match_from_the_api_is_the_match_the_seed_gives(client):
    stream, _ = follow(client, start(client, seed=5, settings={"hand_size": 2})["id"])

    plugin = ToyGame()
    same = Match(plugin, random_bots(plugin, ["p1", "p2"], 5), seed=5, settings={"hand_size": 2})
    asyncio.run(same.run())
    assert as_events(stream) == same.events
    assert replay(plugin, as_events(stream)) == same.state


def test_seed_is_chosen_when_none_is_given(client):
    first, second = start(client), start(client)

    assert first["seed"] != second["seed"]
    assert first["players"] == ["p1", "p2"]  # the game's minimum


def test_running_match_is_streamed_turn_by_turn(client):
    match = start(client, seed=3, turn_delay=0.1)

    with client.websocket_connect(f"/matches/{match['id']}/events") as stream:
        first = stream.receive_json()
        while_running = client.get(f"/matches/{match['id']}").json()
        so_far = client.get(f"/matches/{match['id']}/events").json()
        rest = []
        try:
            while True:
                rest.append(stream.receive_json())
        except WebSocketDisconnect:
            pass

    # The first event arrived while the match was still being played.
    assert first["type"] == "match_started"
    assert while_running["status"] == "running"
    assert 0 < len(so_far) < 1 + len(rest)
    assert rest[-1]["type"] == "match_finished"
    record = client.get(f"/matches/{match['id']}").json()
    assert record["status"] == "finished"
    # Six turns and the end of the match each waited for the delay.
    played_for = datetime.fromisoformat(record["finished_at"]) - datetime.fromisoformat(
        record["started_at"]
    )
    assert played_for.total_seconds() >= 0.6
    # Whoever joins later gets the same log from the start.
    assert follow(client, match["id"]) == ([first, *rest], 1000)


def test_matches_are_listed_newest_first_and_by_status(client):
    older, newer = start(client), start(client)
    follow(client, older["id"]), follow(client, newer["id"])
    slow = start(client, turn_delay=5)

    everything = client.get("/matches").json()
    finished = client.get("/matches", params={"status": "finished"}).json()
    running = client.get("/matches", params={"status": "running"}).json()
    both = client.get("/matches", params={"status": ["running", "failed"]}).json()

    assert [m["id"] for m in everything] == [slow["id"], newer["id"], older["id"]]
    assert [m["id"] for m in finished] == [newer["id"], older["id"]]
    assert [m["id"] for m in running] == [m["id"] for m in both] == [slow["id"]]
    assert client.get("/matches", params={"status": "sleeping"}).status_code == 422


@pytest.mark.parametrize(
    ("body", "status", "detail"),
    [
        ({"game": "chess"}, 404, "Unknown game 'chess'. Games: "),
        ({"game": "toy", "players": 9}, 422, "toy needs 2 to 4 players, got 9"),
        ({"game": "toy", "settings": {"hand_size": 99}}, 422, "hand_size must be"),
        ({"game": "toy", "settings": {"jokers": 2}}, 422, "Unknown settings for toy"),
    ],
)
def test_match_that_cannot_be_played_is_refused_with_the_reason(client, body, status, detail):
    response = client.post("/matches", json=body)

    assert response.status_code == status
    assert detail in response.json()["detail"]
    assert client.get("/matches").json() == []


@pytest.mark.parametrize(
    "body", [{}, {"game": "toy", "seed": -1}, {"game": "toy", "turn_delay": 61}]
)
def test_malformed_request_is_refused(client, body):
    assert client.post("/matches", json=body).status_code == 422
    assert client.get("/matches").json() == []


def test_unknown_match_is_not_found(client):
    unknown = uuid4()

    assert client.get(f"/matches/{unknown}").status_code == 404
    assert client.get(f"/matches/{unknown}/events").status_code == 404
    assert follow(client, unknown) == ([], 4404)


def test_match_stopped_by_a_shutdown_is_marked_and_keeps_its_log(database_url, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", database_url)
    with TestClient(app) as client:
        match = start(client, turn_delay=30)
        with client.websocket_connect(f"/matches/{match['id']}/events") as stream:
            first = stream.receive_json()

    with TestClient(app) as restarted:
        record = restarted.get(f"/matches/{match['id']}").json()
        log, close_code = follow(restarted, match["id"])

    assert record["status"] == "interrupted"
    assert record["finished_at"] is not None and record["placements"] is None
    # What was played is still there, and the stream of a stopped match ends at once.
    assert (log[0], close_code) == (first, 1000)
    assert log[-1]["type"] != "match_finished"


def test_match_left_running_by_a_dead_server_is_marked_at_the_next_start(database_url, monkeypatch):
    match_id = uuid4()

    async def leave_one_running():
        pool = await connect(database_url)
        try:
            await migrate(pool)
            await MatchStore(pool).create(match_id, "toy", ["p1", "p2"], 1, {})
        finally:
            await pool.close()

    asyncio.run(leave_one_running())
    monkeypatch.setenv("DATABASE_URL", database_url)

    with TestClient(app) as client:
        assert client.get(f"/matches/{match_id}").json()["status"] == "interrupted"


def test_match_of_a_broken_game_fails_and_says_so(database_url, monkeypatch, fake_games, caplog):
    fake_games(broken=NEVER_ENDS)
    monkeypatch.setenv("DATABASE_URL", database_url)

    with TestClient(app) as client:
        response = client.post("/matches", json={"game": "broken"})
        log, close_code = follow(client, response.json()["id"])
        record = client.get(f"/matches/{response.json()['id']}").json()

    # The turns before the bug are in the log; the server is still up and the stream ended.
    assert [message["type"] for message in log if message["source"] == "game"] == ["added", "added"]
    assert close_code == 1000
    assert (record["status"], record["placements"]) == ("failed", None)
    assert "made no progress" in caplog.text


def test_match_of_a_game_that_never_ends_stops_at_the_turn_limit_and_fails(
    database_url, monkeypatch, fake_games
):
    fake_games(endless=NEVER_OVER)
    monkeypatch.setenv("DATABASE_URL", database_url)

    with TestClient(app) as client:
        match = client.post("/matches", json={"game": "endless"}).json()
        log, close_code = follow(client, match["id"], at_most=1000)
        record = client.get(f"/matches/{match['id']}").json()
        stored = client.get(f"/matches/{match['id']}/events").json()

    # The match did not fill the database: forty turns, then the reason, then nothing.
    assert [message["type"] for message in log].count("action_accepted") == 40
    assert (log[-1]["type"], log[-1]["data"]) == ("turn_limit_reached", {"max_turns": 40})
    assert close_code == 1000
    assert (record["status"], record["placements"]) == ("failed", None)
    assert stored == log


def test_server_plays_only_so_many_matches_at_a_time(client, monkeypatch):
    monkeypatch.setattr(live, "MAX_RUNNING", 2)
    slow = start(client, turn_delay=30)
    quick = start(client)
    follow(client, quick["id"])  # until it has ended and its place is free again
    second_slow = start(client, turn_delay=30)

    refused = client.post("/matches", json={"game": "toy"})
    wrong = client.post("/matches", json={"game": "toy", "players": 9})

    assert refused.status_code == 429
    assert "2 matches are running" in refused.json()["detail"]
    # A request that could not be played anyway is told why, not to come back later.
    assert wrong.status_code == 422
    running = client.get("/matches", params={"status": "running"}).json()
    assert sorted(m["id"] for m in running) == sorted([slow["id"], second_slow["id"]])
    assert len(client.get("/matches").json()) == 3


def test_match_that_could_not_be_recorded_does_not_keep_its_place(client, monkeypatch):
    monkeypatch.setattr(live, "MAX_RUNNING", 1)
    matches = client.app.state.live.matches

    async def database_is_down(*arguments, **options):
        raise ConnectionError("no database")

    with monkeypatch.context() as broken:
        broken.setattr(matches, "create", database_is_down)
        with pytest.raises(ConnectionError):
            client.post("/matches", json={"game": "toy"})

    # The one place is still free.
    assert start(client)["status"] == "running"


def leaderboard_games(client):
    rows = client.get("/leaderboard", params={"game": "toy"}).json()["rows"]
    return {row["name"]: row["games_played"] for row in rows}


def test_finished_match_rates_its_bots_once(client):
    match = start(client, players=3, seed=1)
    follow(client, match["id"])

    rows = client.get("/leaderboard", params={"game": "toy"}).json()["rows"]
    assert {row["name"]: row["games_played"] for row in rows} == {
        "Random Bot p1": 1,
        "Random Bot p2": 1,
        "Random Bot p3": 1,
    }
    assert {row["model_id"] for row in rows} == {"random-bot"}
    # Ratings follow the placements: the winner is on top and gained points.
    placements = client.get(f"/matches/{match['id']}").json()["placements"]
    winner = next(p["player"] for p in placements if p["rank"] == 1)
    assert rows[0]["name"] == f"Random Bot {winner}"
    assert rows[0]["rating"] > 1000

    # The same bot names in the next match are the same profiles, rated again.
    follow(client, start(client, players=3, seed=2)["id"])
    assert set(leaderboard_games(client).values()) == {2}


def test_applying_the_same_match_again_changes_nothing(client):
    match = start(client, players=2, seed=4)
    follow(client, match["id"])
    before = client.get("/leaderboard", params={"game": "toy"}).json()

    async def again():
        pool = await connect(os.environ["DATABASE_URL"])
        try:
            store = RatingStore(pool)
            profiles = await store.bot_profiles(["p1", "p2"])
            placements = [
                Placement(player=str(profiles[p["player"]]), rank=p["rank"])
                for p in client.get(f"/matches/{match['id']}").json()["placements"]
            ]
            return await store.apply_match_result(UUID(match["id"]), "toy", placements)
        finally:
            await pool.close()

    assert asyncio.run(again()) is None
    assert client.get("/leaderboard", params={"game": "toy"}).json() == before
