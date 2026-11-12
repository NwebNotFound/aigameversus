"""The transcript: coverage of every event type, spoilers, no raw JSON, and golden files."""

import ast
import asyncio
import json
import os
import re
from pathlib import Path

import pytest

from arena.agents.random_bot import random_bots
from arena.engine.match import Match
from arena.engine.types import Event, EventSource
from arena.games import load_games
from arena.transcript import (
    LANGS,
    RENDERERS,
    Transcriber,
    TranscriptError,
    display_names,
    from_export,
    known_event_types,
    labels,
    render_event,
    render_match,
    to_markdown,
    to_text,
)

ROOT = Path(__file__).resolve().parents[2]
GOLDEN = Path(__file__).parent / "golden"
GAMES = {
    "toy": (3, {}),
    "liars_deck": (4, {}),
    "poker": (3, {"hand_limit": 4}),
    "werewolf": (8, {}),
    "civ": (4, {}),
}
# A seeded Throne of Tokens match is 60 rounds, thousands of lines: too long for a golden file.
GOLDEN_GAMES = sorted(set(GAMES) - {"civ"})
ENGINE_TYPES = {
    "match_started",
    "thought",
    "action_accepted",
    "action_rejected",
    "action_fallback",
    "agent_failed",
    "match_paused",
    "match_resumed",
    "turn_limit_reached",
    "match_finished",
}
KINDS = {
    "heading",
    "action",
    "speech",
    "whisper",
    "thought",
    "reveal",
    "result",
    "narration",
    "info",
}


def emitted_types(game: str) -> set[str]:
    """Every event type a plugin of `game` emits, read from its source (a run misses rare ones)."""
    types: set[str] = set()
    for path in (ROOT / "games" / game).glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            is_emit = (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "emit"
                and node.args
            )
            if is_emit:
                first = node.args[0]
                if isinstance(first, ast.Constant):
                    types.add(first.value)
                elif isinstance(first, ast.Name) and first.id == "MESSAGE":
                    types.add("message")
    return types


@pytest.mark.parametrize("game", sorted(GAMES))
def test_every_event_type_a_plugin_emits_has_a_renderer(game):
    missing = emitted_types(game) - known_event_types(game)

    assert not missing, f"{game} emits {sorted(missing)} but the transcript cannot write them"


def test_the_engine_events_have_a_renderer_in_every_game():
    for game in GAMES:
        assert known_event_types(game) >= ENGINE_TYPES


def test_every_game_with_a_plugin_has_a_transcript():
    assert set(load_games()) <= set(RENDERERS)


def bot_events(game: str, seed: int = 7) -> list[Event]:
    players, settings = GAMES[game]
    plugin = load_games()[game]
    names = [f"p{i}" for i in range(1, players + 1)]
    match = Match(plugin, random_bots(plugin, names, seed), seed=seed, settings=settings)
    asyncio.run(match.run())
    return match.events


@pytest.mark.parametrize("game", sorted(GAMES))
@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize("spoilers", [False, True])
def test_a_real_bot_match_renders_every_event_as_plain_words(game, lang, spoilers):
    for seed in (1, 2, 3):
        lines = render_match(bot_events(game, seed), lang=lang, spoilers=spoilers)

        assert lines
        for line in lines:
            assert line.kind in KINDS
            assert line.importance in (1, 2, 3)
            assert not any(mark in line.text for mark in ('{"', "'player'", '":', "[{"))
            assert line.raw["type"]
        assert lines[-1].kind == "result" and lines[-1].importance == 3


@pytest.mark.parametrize("game", sorted(GAMES))
def test_without_spoilers_nothing_private_is_written_but_public_talk_stays(game):
    events = bot_events(game, 2)
    hidden = {i for i, e in enumerate(events) if e.visible_to is not None}

    lines = render_match(events, spoilers=False)
    shown = {line.seq for line in lines}

    assert shown.isdisjoint(hidden - {0})  # match_started is shown, without its seed
    assert all(line.kind not in ("thought", "whisper") for line in lines)
    public_talk = [i for i, e in enumerate(events) if e.type == "message" and e.visible_to is None]
    assert set(public_talk) <= shown


def test_the_seed_is_only_in_the_spoiler_view():
    events = bot_events("liars_deck")

    plain = render_match(events, spoilers=False)[0].text
    full = render_match(events, spoilers=True)[0].text

    assert "seed" not in plain and "seed 7" in full


@pytest.mark.parametrize("game", sorted(GAMES))
def test_the_seed_is_nowhere_in_a_transcript_without_spoilers_not_even_in_raw(game):
    lines = render_match(bot_events(game), spoilers=False)

    dumped = json.dumps([line.model_dump() for line in lines])
    full = json.dumps([line.model_dump() for line in render_match(bot_events(game), spoilers=True)])

    assert "seed" not in dumped
    assert '"seed"' in full


def started(settings: dict, spoilers: bool) -> dict:
    event = Event(
        source=EventSource.ENGINE,
        type="match_started",
        data={"game": "werewolf", "players": ["p1", "p2"], "seed": 7, "settings": settings},
    )
    return render_match([event], spoilers=spoilers)[0].raw["data"]["settings"]


def test_the_role_mix_is_not_in_raw_without_spoilers_unless_roles_are_public():
    mix = {"template": "classic", "roles": {"seer": 1}, "language": "de", "captain": True}

    assert started(mix, spoilers=False) == {"language": "de", "captain": True}
    assert started({**mix, "roles_public": True}, spoilers=False) == {**mix, "roles_public": True}
    assert started(mix, spoilers=True) == mix


def test_german_and_english_differ_and_names_are_used():
    events = bot_events("liars_deck")
    names = labels({"p1": "glm", "p2": "gpt", "p3": "claude", "p4": "gemini"})

    en = to_text(render_match(events, names, "en"))
    de = to_text(render_match(events, names, "de"))

    assert "Round 1, table card" in en and "Runde 1, Tischkarte" in de
    assert "glm" in en and "glm" in de and "p1" not in en and "p1" not in de
    assert en != de


def test_every_seat_gets_one_unique_display_name_and_never_its_seat_id():
    shown = display_names(
        {
            "p1": ("model", "gpt-luna"),
            "p2": ("bot", "Random Bot p2"),
            "p3": ("model", "gpt-luna"),
            "p4": ("model", "gemini-flash-lite"),
            "p5": ("bot", "Random Bot p5"),
        }
    )

    assert shown == {
        "p1": "gpt-luna #1",
        "p2": "Bot 2",
        "p3": "gpt-luna #2",
        "p4": "gemini-flash-lite",
        "p5": "Bot 5",
    }
    assert len(set(shown.values())) == len(shown)


def test_the_display_names_replace_the_seat_ids_in_every_line_of_every_game():
    for game in GAMES:
        events = bot_events(game)
        start = next(e for e in events if e.type == "match_started")
        names = display_names({p: ("bot", p) for p in start.data["players"]})

        for lang in LANGS:
            for line in render_match(events, names, lang, spoilers=True):
                assert not re.search(r"p\d+", line.text), (game, lang, line.text)


def test_one_event_alone_is_a_line_and_the_log_gives_context():
    events = bot_events("poker")
    flop = next(e for e in events if e.type == "street_started" and e.data["street"] == "flop")

    alone = render_event("poker", flop, ["p1", "p2", "p3"], "en")
    turns = [
        line
        for line in render_match(events)
        if line.raw["type"] == "street_started" and line.text.startswith("Turn: ")
    ]

    assert alone is not None and alone.text.startswith("Flop: ")
    assert turns and all("board" in line.text for line in turns)


def test_unknown_game_language_and_event_are_errors():
    with pytest.raises(TranscriptError, match="no transcript"):
        Transcriber("chess")
    with pytest.raises(TranscriptError, match="unknown language"):
        Transcriber("toy", lang="fr")
    odd = Event(source=EventSource.GAME, type="surprise", data={})
    with pytest.raises(KeyError, match="no renderer"):
        render_event("toy", odd)


def test_text_and_markdown_fold_by_importance():
    lines = render_match(bot_events("liars_deck"), lang="en")

    everything = to_text(lines, min_importance=1)
    highlights = to_text(lines, min_importance=3)
    markdown = to_markdown(lines, min_importance=2)

    assert len(highlights.splitlines()) < len(everything.splitlines())
    assert "is next" in everything and "is next" not in highlights
    assert markdown.startswith("## ") and "\n- **" in markdown


def test_a_saved_match_file_renders_with_its_model_names():
    path = ROOT / "docs" / "examples" / "liars_deck.json"
    game, events, names = from_export(json.loads(path.read_text(encoding="utf-8")))

    text = to_text(render_match(events, names, "de", game=game), min_importance=2)

    assert game == "liars_deck" and "glm-flash" in text and "Runde 1" in text
    assert "p1 (" not in text and "p1 legt" not in text  # models may say p1 in their own words


def test_a_replay_export_renders_too():
    events = bot_events("toy")
    export = {
        "format": "aigameversus-replay/1",
        "match": {"game": "toy", "players": ["p1", "p2", "p3"]},
        "events": [e.model_dump(mode="json") for e in events],
    }

    game, loaded, names = from_export(export)

    assert game == "toy" and names == {"p1": "p1", "p2": "p2", "p3": "p3"}
    assert render_match(loaded, names, game=game)


def test_a_file_that_is_not_a_match_is_refused():
    with pytest.raises(TranscriptError, match="not a saved match"):
        from_export({"hello": "world"})


# --- golden files -------------------------------------------------------------


def check_golden(name: str, text: str) -> None:
    path = GOLDEN / name
    if os.environ.get("UPDATE_GOLDEN"):
        path.write_text(text, encoding="utf-8", newline="\n")
    assert path.exists(), f"{name} is missing; run with UPDATE_GOLDEN=1"
    assert text == path.read_text(encoding="utf-8"), f"{name} changed; UPDATE_GOLDEN=1 if intended"


@pytest.mark.parametrize("game", GOLDEN_GAMES)
@pytest.mark.parametrize("lang", LANGS)
def test_golden_seeded_bot_match_with_spoilers(game, lang):
    lines = render_match(bot_events(game, 7), lang=lang, spoilers=True)

    check_golden(f"{game}_{lang}.txt", to_text(lines))


@pytest.mark.parametrize("game", ["liars_deck", "poker", "werewolf"])
def test_golden_real_model_match_as_the_public_saw_it(game):
    data = json.loads((ROOT / "docs" / "examples" / f"{game}.json").read_text(encoding="utf-8"))
    game_id, events, names = from_export(data)

    lines = render_match(events, names, "en", spoilers=False, game=game_id)

    check_golden(f"example_{game}_en.txt", to_text(lines))
