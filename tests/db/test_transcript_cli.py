"""`arena transcript <match id>` reads a stored match from the database."""

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from arena.api.app import app
from arena.cli import main


@pytest.fixture
def stored_match(database_url, monkeypatch):
    """A finished liars_deck match of three bots, stored in a throwaway schema."""
    monkeypatch.setenv("DATABASE_URL", database_url)
    with TestClient(app) as client:
        match_id = client.post(
            "/matches", json={"game": "liars_deck", "players": 3, "seed": 5}
        ).json()["id"]
        with client.websocket_connect(f"/matches/{match_id}/events") as stream:
            try:
                while True:
                    stream.receive_json()
            except WebSocketDisconnect:
                pass
    return match_id


def test_a_stored_match_is_printed_with_the_names_of_its_profiles(stored_match, capsys):
    code = main(["transcript", stored_match, "--lang", "de"])

    out = capsys.readouterr().out
    assert code == 0
    assert "Runde 1, Tischkarte:" in out
    assert "Random Bot p1" in out and "(random-bot)" not in out
    assert "{" not in out


def test_follow_prints_a_finished_match_and_stops(stored_match, capsys):
    code = main(["transcript", stored_match, "--follow"])

    out = capsys.readouterr().out
    assert code == 0
    assert out.splitlines()[0].startswith("Match started:")
    assert "Result:" in out.splitlines()[-1]


def test_an_unknown_match_id_is_explained(stored_match, capsys):
    with pytest.raises(SystemExit) as stop:
        main(["transcript", "00000000-0000-0000-0000-000000000000"])

    assert stop.value.code == 2
    assert "no match 00000000-0000-0000-0000-000000000000" in capsys.readouterr().err
