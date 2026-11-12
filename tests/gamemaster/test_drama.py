"""The game master's dramatic lines for Werewolf narration: varied, named, only the facts."""

import asyncio
import re

import pytest

from arena.agents.random_bot import random_bots
from arena.analytics import match_analytics
from arena.engine.match import Match
from arena.engine.types import Event, EventSource
from arena.gamemaster import drama
from arena.games import load_games
from games.werewolf.narrator import TEMPLATES

SEATS = [f"p{i}" for i in range(1, 11)]
NAMES = {seat: f"Seat {chr(64 + i)}" for i, seat in enumerate(SEATS, start=1)}


def narration(key, data, seq):
    event = Event(
        source=EventSource.GAME,
        type="narration",
        data={"key": key, "data": data, "text": "plain", "language": "en"},
    )
    return (seq, event)


def test_every_moment_the_game_narrates_has_dramatic_lines_in_both_languages():
    assert set(drama.LINES) == set(TEMPLATES["en"]) == set(TEMPLATES["de"])
    for key, langs in drama.LINES.items():
        assert langs["en"] and langs["de"], key


def test_the_same_moment_twice_reads_differently_and_a_replay_reads_the_same():
    log = [narration("night_falls", {"night": n}, seq) for seq, n in ((3, 1), (40, 2), (90, 3))]

    first = drama.narration(log, {})
    again = drama.narration(log, {})

    assert first == again
    texts = [line["text"]["en"] for line in first]
    assert len(set(re.sub(r"\d", "", t) for t in texts)) == 3  # three different variants
    assert [line["seq"] for line in first] == [3, 40, 90]


def test_a_line_names_players_by_display_name_and_roles_in_each_language():
    log = [
        narration("execution", {"player": "p3", "role": "seer"}, 10),
        narration("morning_deaths", {"deaths": [{"player": "p1", "role": "witch"}]}, 20),
    ]

    lines = drama.narration(log, {"p3": "gpt-luna #1", "p1": "Bo"})

    assert "gpt-luna #1" in lines[0]["text"]["en"] and "the seer" in lines[0]["text"]["en"]
    assert "Seherin" in lines[0]["text"]["de"]
    assert "Bo (the witch)" in lines[1]["text"]["en"] and "Bo (Hexe)" in lines[1]["text"]["de"]


def test_a_key_without_lines_keeps_the_games_own_text():
    (line,) = drama.narration([narration("something_new", {}, 5)], {})

    assert line["text"] == {"en": "plain", "de": "plain"}


def test_a_voice_can_replace_the_template_and_falls_back_when_it_says_nothing():
    class Shy:
        def speak(self, key, data, lang, name, pick):
            return None if key == "night_falls" else f"{lang}:{key}"

    log = [narration("night_falls", {"night": 1}, 1), narration("morning_quiet", {}, 2)]

    lines = drama.narration(log, {}, voice=Shy())

    assert lines[0]["text"]["en"] == "plain"
    assert lines[1]["text"] == {"en": "en:morning_quiet", "de": "de:morning_quiet"}


@pytest.mark.parametrize("seed", [1, 2, 3, 4])
def test_bot_matches_get_a_named_line_for_every_narration_event(seed):
    plugin = load_games()["werewolf"]
    match = Match(plugin, random_bots(plugin, SEATS, seed), seed=seed)
    asyncio.run(match.run())

    lines = match_analytics("werewolf", match.events, False, NAMES)["narration"]

    narrated = [seq for seq, e in enumerate(match.events) if e.type == "narration"]
    assert [line["seq"] for line in lines] == narrated
    for line in lines:
        for text in line["text"].values():
            assert text and not re.search(r"\bp\d+\b", text), text
            assert "{" not in text, text
