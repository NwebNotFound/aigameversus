"""The API behind a real server on a real port, as the Compose stack runs it.

The other API tests use FastAPI's test client, which never opens a socket. This
one does, so it also fails when the server cannot speak WebSocket at all.
"""

import json
import threading
import time
import urllib.request

import pytest
import uvicorn
from websockets.sync.client import connect

from arena.api.app import app


@pytest.fixture
def server_address(database_url, monkeypatch):
    """Host and port of the arena API, served by uvicorn for the length of the test."""
    monkeypatch.setenv("DATABASE_URL", database_url)
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning"))
    thread = threading.Thread(target=server.run)
    thread.start()
    try:
        deadline = time.monotonic() + 20
        while not server.started:
            assert thread.is_alive() and time.monotonic() < deadline, "The server did not start"
            time.sleep(0.02)
        port = server.servers[0].sockets[0].getsockname()[1]
        yield f"127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(20)


def test_match_started_over_http_is_streamed_over_websocket(server_address):
    request = urllib.request.Request(
        f"http://{server_address}/matches",
        data=json.dumps({"game": "toy", "seed": 7, "turn_delay": 0.05}).encode(),
        headers={"content-type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        match = json.load(response)

    with connect(f"ws://{server_address}/matches/{match['id']}/events") as stream:
        events = [json.loads(message) for message in stream]  # until the server closes

    assert [event["seq"] for event in events] == list(range(len(events)))
    assert (events[0]["type"], events[-1]["type"]) == ("match_started", "match_finished")
    assert events[0]["data"]["seed"] == 7
    with urllib.request.urlopen(f"http://{server_address}/matches/{match['id']}") as response:
        assert json.load(response)["status"] == "finished"
