"""The Throne of Tokens play-by-play: public lines without spoilers, readable cities and armies."""

import asyncio
import json
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


def test_without_spoilers_the_rounds_say_where_cities_stand_and_who_won_battles(events):
    lines = render_match(events, NAMES, spoilers=False)
    kinds = {line.raw["type"] for line in lines}

    assert {"round_started", "city_founded", "battle"} <= kinds
    founded = [line.text for line in lines if line.raw["type"] == "city_founded"]
    assert all("Bot" in text and "(" in text for text in founded)
    battle = next(line for line in lines if line.raw["type"] == "battle")
    assert "wins" in battle.text and battle.detail is None  # no losses without spoilers


def test_the_round_heading_carries_the_public_city_count_of_every_nation(events):
    lines = render_match(events, NAMES, spoilers=False)
    headings = [line for line in lines if line.raw["type"] == "round_started"]

    assert headings[0].detail == "Cities: Bot 1 1, Bot 2 1, Bot 3 1, Bot 4 1"
    assert all(line.detail and line.detail.startswith("Cities: ") for line in headings)
    german = render_match(events, NAMES, lang="de", spoilers=False)
    assert next(line for line in german if line.raw["type"] == "round_started").detail.startswith(
        "Städte: "
    )


def test_a_battle_in_the_public_view_leaks_no_power_and_no_losses(events):
    for line in render_match(events, NAMES, spoilers=False):
        if line.raw["type"] == "battle":
            assert set(line.raw["data"]) <= {"tile", "winner", "attacker", "defender"}
            assert set(line.raw["data"].get("attacker", {})) <= {"nation"}
            assert "power" not in json.dumps(line.raw) and "lost" not in json.dumps(line.raw)


def test_nothing_else_private_appears_without_spoilers(events):
    shown = {line.raw["type"] for line in render_match(events, NAMES, spoilers=False)}
    private = {e.type for e in events if e.visible_to is not None}

    assert (shown & private) <= {"city_founded", "battle", "match_started"}


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
