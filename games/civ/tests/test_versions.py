"""Rules versions: a match keeps the rules it was played with (match_started's `version`).

`golden/v1_match.json` is a bot match recorded with rules version 1, before D-137 and
D-138, by the code of that time. It must keep replaying to the same state, and version 1
must still play it event for event.
"""

import asyncio
import json
from pathlib import Path

import pytest

from arena.agents.random_bot import random_bots
from arena.engine.match import Match
from arena.engine.replay import ReplayError, plugin_for, replay
from arena.engine.types import Event
from games.civ.plugin import RULES, CivGame

GOLDEN = json.loads((Path(__file__).parent / "golden" / "v1_match.json").read_text("utf-8"))
EVENTS = [Event(**event) for event in GOLDEN["events"]]


def play(plugin: CivGame) -> Match:
    bots = random_bots(plugin, GOLDEN["players"], GOLDEN["bots_seed"])
    match = Match(plugin, bots, seed=GOLDEN["seed"], settings=GOLDEN["settings"])
    asyncio.run(match.run())
    return match


def test_the_newest_plugin_replays_a_version_1_log_to_the_state_it_had_then():
    assert EVENTS[0].data["version"] == "1" and CivGame().version != "1"

    state = replay(CivGame(), EVENTS)

    assert state.model_dump(mode="json") == GOLDEN["final_state"]


def test_version_1_still_plays_the_recorded_match_event_for_event():
    match = play(CivGame("1"))

    assert [e.model_dump(mode="json") for e in match.events] == GOLDEN["events"]


def test_the_newest_rules_play_the_same_seed_differently():
    newest = play(CivGame())

    assert newest.events[0].data["version"] == CivGame.version
    assert [e.model_dump(mode="json") for e in newest.events] != GOLDEN["events"]


def test_a_log_without_a_version_is_version_1():
    start = EVENTS[0].model_copy(
        update={"data": {k: v for k, v in EVENTS[0].data.items() if k != "version"}}
    )

    assert plugin_for(CivGame(), start).version == "1"
    assert replay(CivGame(), [start, *EVENTS[1:]]).model_dump(mode="json") == GOLDEN["final_state"]


def test_an_unknown_version_is_refused_with_a_reason():
    start = EVENTS[0].model_copy(update={"data": {**EVENTS[0].data, "version": "9"}})

    with pytest.raises(ReplayError, match="recorded with civ version 9"):
        replay(CivGame(), [start, *EVENTS[1:]])
    with pytest.raises(ValueError, match="no rules version 9"):
        CivGame("9")


def test_each_version_keeps_its_own_data_and_the_board_of_an_old_log_is_drawn_with_it():
    old, new = RULES["1"], RULES["2"]
    assert old.victory.domination.min_cities_per_nation == 0
    assert new.victory.domination.min_cities_per_nation == 2
    assert old.balance.map.start_regions["food"] != new.balance.map.start_regions["food"]

    plugin = plugin_for(CivGame(), EVENTS[0])
    board = plugin.render_spec(replay(plugin, EVENTS))

    assert plugin.data is old and board["round"] == GOLDEN["final_state"]["round"]
