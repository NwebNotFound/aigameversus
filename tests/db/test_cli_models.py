"""`arena run --models`: real model seats from the command line.

LiteLLM answers from its built-in mock and every name lookup is refused, so
nothing here reaches a provider or costs money. The ledger is a real one.
"""

import asyncio
import json
import re
from decimal import Decimal

import pytest

from arena import cli
from arena.config import load_config
from arena.db.database import connect, migrate
from arena.db.event_store import EventStore
from arena.db.match_store import MatchStore
from arena.engine.replay import replay
from games.toy.plugin import ToyGame
from tests.test_cli import arena

KEY = "THIS-IS-THE-SECRET-KEY"  # not shaped like a real key, so secret scanners stay quiet
CALL = {"id": "call_1", "type": "function"}
PLAY_3 = {
    "mock_response": "A three should do.",
    "mock_tool_calls": [{**CALL, "function": {"name": "play_card", "arguments": '{"card": 3}'}}],
}


@pytest.fixture
def database(database_url, monkeypatch):
    """The command stores into an empty schema, and a key is set that must show up nowhere."""
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("OPENROUTER_API_KEY", KEY)
    return database_url


def stored(database_url):
    """Every match in the database with its events, and every booked model call."""

    async def read():
        pool = await connect(database_url)
        try:
            await migrate(pool)  # a command that was refused has not made the tables
            matches = await MatchStore(pool).recent()
            events = {match.id: await EventStore(pool).load(match.id) for match in matches}
            calls = await pool.fetch(
                "SELECT match_id, player, model, cost_micro_eur FROM model_calls ORDER BY id"
            )
            return matches, events, [tuple(call) for call in calls]
        finally:
            await pool.close()

    return asyncio.run(read())


def test_models_play_a_match_that_is_stored_metered_and_rebuilt(database, answer_with, capsys):
    sent = answer_with(**PLAY_3)

    code, output, complaints = arena(
        capsys,
        "run",
        "--game",
        "toy",
        "--models",
        "glm-flash,deepseek-flash",
        "--seed",
        "7",
        "--raw",  # this test reads the events as stored
    )

    assert (code, complaints) == (0, "")
    assert sent["model"] in (
        "openrouter/z-ai/glm-5.3-flash",
        "openrouter/deepseek/deepseek-v4.1-flash",
    )
    (match,), events, calls = stored(database)
    lines = output.splitlines()
    assert lines[0] == f"High Card (toy), match {match.id}, seed 7"
    assert lines[1] == "Seats: p1 glm-flash  p2 deepseek-flash"

    # The match is on record as finished, with the result the command printed.
    assert (match.game, match.status, match.players, match.seed) == (
        "toy",
        "finished",
        ["p1", "p2"],
        7,
    )
    ranking = sorted(match.placements, key=lambda placement: placement.rank)
    assert lines[-3] == "Result: " + "  ".join(f"{p.rank}. {p.player}" for p in ranking)

    # Every event that was printed is stored, and the stored log is a whole match.
    log = events[match.id]
    printed = [line for line in lines if re.match(r" *\d+  \w+ ", line)]
    assert len(printed) == len(log)
    assert (log[0].type, log[-1].type) == ("match_started", "match_finished")
    assert replay(ToyGame(), log).tricks_won
    assert lines[-1] == f"Replay: the {len(log)} stored events rebuild the final state"

    # Every call is in the ledger under its seat and model, and the command adds them up.
    assert {(player, model) for _, player, model, _ in calls} == {
        ("p1", "glm-flash"),
        ("p2", "deepseek-flash"),
    }
    assert all(match_id == match.id and cost > 0 for match_id, _, _, cost in calls)
    cost = {player: sum(c for _, p, _, c in calls if p == player) for player in ("p1", "p2")}
    assert lines[-2] == (
        f"Cost: p1 {cost['p1'] / 1e6:.6f}  p2 {cost['p2'] / 1e6:.6f}  "
        f"total {sum(cost.values()) / 1e6:.6f} EUR of 0.500000 EUR"
    )
    assert KEY not in output + complaints


def test_match_can_be_saved_as_a_file_with_seats_cost_and_every_event(
    database, answer_with, capsys, tmp_path
):
    answer_with(**PLAY_3)
    file = tmp_path / "match.json"

    code, output, _ = arena(
        capsys,
        "run", "--game", "toy", "--models", "glm-flash,llama-scout,glm-flash",
        "--seed", "3", "--setting", "hand_size=2", "--save", str(file),
    )  # fmt: skip

    assert code == 0
    (match,), events, calls = stored(database)
    saved = json.loads(file.read_text(encoding="utf-8"))
    assert saved["match"] == str(match.id)
    assert (saved["game"], saved["version"], saved["seed"]) == ("toy", ToyGame.version, 3)
    assert saved["settings"] == match.settings
    assert saved["seats"] == {"p1": "glm-flash", "p2": "llama-scout", "p3": "glm-flash"}
    assert saved["status"] == "finished"
    assert saved["placements"] == [placement.model_dump() for placement in match.placements]
    assert saved["cost_micro_eur"] == {
        player: sum(c for _, p, _, c in calls if p == player) for player in ("p1", "p2", "p3")
    }
    assert saved["events"] == [event.model_dump(mode="json") for event in events[match.id]]
    assert KEY not in file.read_text(encoding="utf-8")


def test_cost_cap_ends_the_match_before_the_call_that_would_pass_it(
    database, answer_with, capsys, monkeypatch, tmp_path
):
    sent = answer_with(**PLAY_3)
    config = load_config()
    tight = config.limits.model_copy(update={"match_eur": Decimal("0.000050")})
    monkeypatch.setattr(cli, "load_config", lambda: config.model_copy(update={"limits": tight}))
    file = tmp_path / "match.json"

    code, output, complaints = arena(
        capsys, "run", "--game", "toy", "--models", "glm-flash,glm-flash", "--save", str(file)
    )

    assert (code, complaints) == (cli.STOPPED_AT_CAP, "")
    assert "Stopped at a cost cap (match_cap)" in output
    assert "Result:" not in output
    assert sent == {}  # no call left the process
    (match,), events, calls = stored(database)
    assert (match.status, match.placements, calls) == ("interrupted", None, [])
    assert [event.type for event in events[match.id]][-1] == "match_paused"
    assert json.loads(file.read_text(encoding="utf-8"))["status"] == "stopped_at_cost_cap"
    assert "total 0.000000 EUR of 0.000050 EUR" in output


def test_stored_log_that_does_not_rebuild_the_state_fails_the_command(
    database, answer_with, capsys, monkeypatch
):
    answer_with(**PLAY_3)
    monkeypatch.setattr(cli, "replay", lambda plugin, events: None)

    code, output, _ = arena(capsys, "run", "--game", "toy", "--models", "glm-flash,glm-flash")

    assert code == 1
    assert output.splitlines()[-1].endswith("stored events DO NOT rebuild the final state")


@pytest.mark.parametrize(
    ("arguments", "complaint"),
    [
        (["--models", "glm-flash,gpt-9"], "unknown model gpt-9; config/models.yaml has: .*glm"),
        (["--models", "glm-flash"], "toy needs 2 to 4 players, got 1"),
        (["--models", "glm-flash,glm-flash", "--setting", "hand_size=99"], "hand_size must be"),
        (["--models", "glm-flash,glm-flash", "--players", "2"], "--players goes with --bots"),
        (["--models", "glm-flash,glm-flash", "--bots"], "not allowed with"),
        (["--bots", "--save", "match.json"], "--save goes with --models"),
    ],
)  # fmt: skip
def test_wrong_call_is_explained_and_nothing_is_played_or_stored(
    database, answer_with, capsys, arguments, complaint
):
    sent = answer_with(**PLAY_3)

    code, output, complaints = arena(capsys, "run", "--game", "toy", *arguments)

    assert (code, output) == (2, "")
    assert re.search(f"arena( run)?: error: .*{complaint}", complaints)
    assert sent == {}
    assert stored(database) == ([], {}, [])


@pytest.mark.parametrize("key", [None, ""])
def test_models_need_the_key_of_their_provider_before_anything_is_booked(
    database, answer_with, capsys, monkeypatch, key
):
    sent = answer_with(**PLAY_3)
    if key is None:
        monkeypatch.delenv("OPENROUTER_API_KEY")
    else:
        monkeypatch.setenv("OPENROUTER_API_KEY", key)

    code, output, complaints = arena(
        capsys, "run", "--game", "toy", "--models", "glm-flash,deepseek-flash"
    )

    assert (code, output) == (2, "")
    assert "--models needs OPENROUTER_API_KEY in the environment" in complaints
    assert sent == {}
    assert stored(database) == ([], {}, [])


def test_models_need_a_database(answer_with, capsys, monkeypatch):
    sent = answer_with(**PLAY_3)
    monkeypatch.setenv("OPENROUTER_API_KEY", KEY)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    code, output, complaints = arena(
        capsys, "run", "--game", "toy", "--models", "glm-flash,glm-flash"
    )

    assert (code, output) == (2, "")
    assert "--models needs DATABASE_URL" in complaints
    assert sent == {}
