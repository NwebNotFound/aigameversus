"""The `arena` command, called the way a person types it."""

import asyncio
import json
import re
import subprocess
import sys
from importlib.metadata import entry_points

import pytest

from arena.agents.random_bot import random_bots
from arena.cli import main
from arena.engine.match import Match
from games.toy.plugin import ToyGame


def arena(capsys, *arguments):
    """Run the command. Returns its exit code, what it printed and what it complained about."""
    try:
        code = main(arguments)
    except SystemExit as exit:
        code = exit.code
    printed = capsys.readouterr()
    return code, printed.out, printed.err


def event_lines(output):
    """The printed events as (position, type, data, audience note)."""
    pattern = re.compile(r"^ *(\d+)  (\w+) +(\{.*?\})(?:  \[(.*)\])?$")
    return [
        (int(seq), type, json.loads(data), audience)
        for seq, type, data, audience in (
            pattern.match(line).groups() for line in output.splitlines()[1:-1]
        )
    ]


def test_bot_match_runs_to_the_end_and_prints_every_event(capsys):
    code, output, complaints = arena(
        capsys, "run", "--game", "toy", "--bots", "--seed", "7", "--raw"
    )

    plugin = ToyGame()
    match = Match(plugin, random_bots(plugin, ["p1", "p2"], 7), seed=7)
    asyncio.run(match.run())
    assert (code, complaints) == (0, "")
    lines = output.splitlines()
    assert lines[0] == "High Card (toy), players p1 p2, seed 7"
    assert [(type, data) for _, type, data, _ in event_lines(output)] == [
        (event.type, event.data) for event in match.events
    ]
    assert [seq for seq, *_ in event_lines(output)] == list(range(len(match.events)))
    ranking = sorted(plugin.results(match.state), key=lambda placement: placement.rank)
    assert lines[-1] == "Result: " + "  ".join(f"{p.rank}. {p.player}" for p in ranking)


def test_output_says_who_may_see_an_event(capsys):
    _, output, _ = arena(capsys, "run", "--game", "toy", "--bots", "--seed", "7", "--raw")

    events = event_lines(output)
    audiences = {type: audience for _, type, _, audience in events}
    assert audiences["match_started"] == "spectators only"
    assert audiences["card_played"] is None
    dealt = [
        (data["player"], audience) for _, type, data, audience in events if type == "hand_dealt"
    ]
    assert dealt == [("p1", "only p1"), ("p2", "only p2")]


def test_same_seed_prints_the_same_match_and_a_random_seed_is_shown(capsys):
    _, first, _ = arena(capsys, "run", "--game", "toy", "--bots", "--raw")
    seed = re.search(r"seed (\d+)$", first.splitlines()[0]).group(1)

    _, again, _ = arena(capsys, "run", "--game", "toy", "--bots", "--seed", seed, "--raw")
    _, other, _ = arena(
        capsys, "run", "--game", "toy", "--bots", "--seed", str(int(seed) + 1), "--raw"
    )

    assert again == first
    assert other != first


def test_players_and_settings_can_be_chosen(capsys):
    code, output, _ = arena(
        capsys, "run", "--game", "toy", "--bots", "--players", "4", "--setting", "hand_size=2",
        "--raw",
    )  # fmt: skip

    assert code == 0
    assert output.splitlines()[0].startswith("High Card (toy), players p1 p2 p3 p4, seed ")
    hands = [data["cards"] for _, type, data, _ in event_lines(output) if type == "hand_dealt"]
    assert [len(hand) for hand in hands] == [2, 2, 2, 2]


def test_games_are_listed(capsys):
    code, output, _ = arena(capsys, "games")

    assert code == 0
    assert "toy          High Card (2 to 4 players)" in output.splitlines()


@pytest.mark.parametrize(
    ("arguments", "complaint"),
    [
        (["run", "--game", "chess", "--bots"], "unknown game 'chess'; choose from: .*toy"),
        (["run", "--game", "toy", "--bots", "--players", "9"], "toy needs 2 to 4 players, got 9"),
        (["run", "--game", "toy", "--bots", "--setting", "hand_size=99"], "hand_size must be"),
        (["run", "--game", "toy", "--bots", "--setting", "hand_size"], "needs NAME=VALUE"),
        (["run", "--game", "toy"], "--bots"),
        (["run", "--bots"], "--game"),
        ([], "command"),
    ],
)
def test_wrong_call_is_explained_and_nothing_is_played(capsys, arguments, complaint):
    code, output, complaints = arena(capsys, *arguments)

    assert code == 2
    assert output == ""
    assert re.search(f"arena( run)?: error: .*{complaint}", complaints)


def test_command_is_installed_and_runs_as_a_program():
    (script,) = entry_points(group="console_scripts", name="arena")
    assert script.value == "arena.cli:main"

    done = subprocess.run(
        [sys.executable, "-m", "arena.cli", "run", "--game", "toy", "--bots", "--seed", "7"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
    )

    assert done.returncode == 0
    assert done.stdout.splitlines()[0] == "High Card (toy), players p1 p2, seed 7"
    assert done.stdout.splitlines()[-1].startswith("Result: ")


def test_a_bot_match_is_printed_as_a_play_by_play_by_default(capsys):
    code, output, _ = arena(capsys, "run", "--game", "liars_deck", "--bots", "--seed", "7")

    assert code == 0
    assert "Round 1, table card:" in output
    assert "calls LIAR on" in output
    assert "{" not in output and "visible_to" not in output
    assert output.splitlines()[-1].startswith("Result: ")


def test_the_language_spoilers_and_bookkeeping_are_chosen_with_flags(capsys):
    _, german, _ = arena(
        capsys, "run", "--game", "liars_deck", "--bots", "--seed", "7", "--lang", "de"
    )
    _, plain, _ = arena(
        capsys, "run", "--game", "liars_deck", "--bots", "--seed", "7", "--no-spoilers"
    )
    _, everything, _ = arena(
        capsys, "run", "--game", "liars_deck", "--bots", "--seed", "7", "--all"
    )
    _, normal, _ = arena(capsys, "run", "--game", "liars_deck", "--bots", "--seed", "7")

    assert "Runde 1, Tischkarte:" in german
    assert "(seed 7)" in normal and "(seed 7)" not in plain
    assert "is next" in everything and "is next" not in normal


def test_a_saved_match_file_is_printed_as_a_transcript(capsys, tmp_path):
    from games.liars_deck.plugin import LiarsDeck

    plugin = LiarsDeck()
    match = Match(plugin, random_bots(plugin, ["p1", "p2", "p3"], 5), seed=5)
    asyncio.run(match.run())
    export = {
        "game": "liars_deck",
        "seats": {"p1": "glm-flash", "p2": "gpt-luna", "p3": "claude-haiku"},
        "events": [e.model_dump(mode="json") for e in match.events],
    }
    path = tmp_path / "match.json"
    path.write_text(json.dumps(export), encoding="utf-8")

    code, text, _ = arena(capsys, "transcript", str(path), "--lang", "de")
    _, markdown, _ = arena(capsys, "transcript", str(path), "--format", "markdown")
    _, as_json, _ = arena(capsys, "transcript", str(path), "--format", "json")

    assert code == 0
    assert "p1 (glm-flash)" in text and "Runde 1, Tischkarte:" in text
    assert markdown.startswith("## ")
    assert {line["kind"] for line in json.loads(as_json)} >= {"heading", "action", "result"}


@pytest.mark.parametrize(
    ("arguments", "complaint"),
    [
        (["transcript", "no-such-file.json"], "neither a file nor a match id"),
        (["transcript", "00000000-0000-0000-0000-000000000000", "--follow"], "DATABASE_URL"),
    ],
)
def test_the_transcript_command_explains_what_it_cannot_do(
    capsys, monkeypatch, arguments, complaint
):
    monkeypatch.delenv("DATABASE_URL", raising=False)

    code, output, complaints = arena(capsys, *arguments)

    assert code == 2 and output == ""
    assert re.search(complaint, complaints)
