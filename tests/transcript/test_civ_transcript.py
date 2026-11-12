"""The Throne of Tokens play-by-play: public lines without spoilers, readable cities and armies."""

import asyncio
import re

import pytest

from arena.agents.random_bot import random_bots
from arena.engine.match import Match
from arena.transcript import render_match
from games.civ.plugin import CivGame

PLAYERS = ["p1", "p2", "p3", "p4"]
NAMES = {"p1": "Bot 1", "p2": "Bot 2", "p3": "Bot 3", "p4": "Bot 4"}


def played(seed=3, rounds=12):
    plugin = CivGame()
    match = Match(
        plugin, random_bots(plugin, PLAYERS, seed), seed=seed, settings={"rounds": rounds}
    )
    asyncio.run(match.run())
    return match.events


@pytest.fixture(scope="module")
def events():
    return played()


def texts(lines):
    return [line.text for line in lines]


def test_without_spoilers_a_founding_shows_who_but_never_where(events):
    lines = render_match(events, NAMES, spoilers=False)
    founded = [line for line in lines if line.raw["type"] == "city_founded"]

    assert founded and all(re.fullmatch(r"Bot \d founds a city", line.text) for line in founded)
    assert all(set(line.raw["data"]) == {"owner"} for line in founded)
    german = render_match(events, NAMES, lang="de", spoilers=False)
    assert any("gründet eine Stadt" in line.text for line in german)


def test_the_round_heading_carries_the_public_city_count_of_every_nation(events):
    lines = render_match(events, NAMES, spoilers=False)
    headings = [line for line in lines if line.raw["type"] == "round_started"]

    assert headings[0].detail == "Cities: Bot 1 1, Bot 2 1, Bot 3 1, Bot 4 1"
    assert all(line.detail and line.detail.startswith("Cities: ") for line in headings)
    german = render_match(events, NAMES, lang="de", spoilers=False)
    assert next(line for line in german if line.raw["type"] == "round_started").detail.startswith(
        "Städte: "
    )


@pytest.mark.parametrize("seed", [1, 2, 3, 5])
def test_the_public_view_names_no_place_of_a_city_nobody_conquered(seed):
    events = played(seed=seed)
    conquered = {e.data["city"] for e in events if e.type == "city_conquered"}
    founded = {
        e.data["city"]: (e.data["col"], e.data["row"]) for e in events if e.type == "city_founded"
    }
    allowed = {founded[c] for c in conquered if c in founded}
    lines = render_match(events, NAMES, spoilers=False)
    text = chr(10).join(line.text + " " + (line.detail or "") for line in lines)

    shown = {(int(a), int(b)) for a, b in re.findall(r"\((\d+), (\d+)\)", text)}
    assert shown <= allowed, shown - allowed
    assert "Battle at" not in text and "Schlacht" not in text
    assert not any(line.raw["type"] == "battle" for line in lines)


def test_nothing_else_private_appears_without_spoilers(events):
    shown = {line.raw["type"] for line in render_match(events, NAMES, spoilers=False)}
    private = {e.type for e in events if e.visible_to is not None}

    assert (shown & private) <= {"city_founded", "match_started"}


def test_cities_and_armies_read_as_who_where_and_how_big(events):
    lines = render_match(events, NAMES, spoilers=True)
    text = "\n".join(texts(lines))

    assert re.search(r"c\d+ \(Bot \d, \(\d+, \d+\)\)", text)  # a city: id, owner, tile
    assert re.search(r"a\d+ \(Bot \d, \d+ units?\)", text)  # an army: id, owner, size
    assert not re.search(r"\bc\d+ (starts|finishes|grows)", text)  # never a bare id as subject


def test_german_labels_use_german_nouns(events):
    text = "\n".join(texts(render_match(events, NAMES, lang="de", spoilers=True)))

    assert re.search(r"a\d+ \(Bot \d, \d+ Einheit", text)


def test_an_army_that_lost_units_shrinks_in_its_label():
    from arena.transcript.civ import Civ

    civ = Civ("en", True, NAMES)
    from arena.engine.types import Event, EventSource

    def game(type, data):
        return Event(source=EventSource.GAME, type=type, data=data, visible_to=["p1"])

    civ.line(
        game(
            "army_raised",
            {"army": "a1", "owner": "p1", "units": [{"kind": "spearman"}] * 3, "col": 1, "row": 1},
        )
    )
    civ.line(game("units_lost", {"army": "a1", "indexes": [0], "reason": "battle"}))

    assert civ.army("a1") == "a1 (Bot 1, 2 units)"
