"""The saved matches in docs/examples: readable, complete, and free of what must not be in them."""

import json
import re
from pathlib import Path

import pytest

from arena.config import load_config
from arena.engine.replay import replay
from arena.engine.types import Event, Placement
from arena.games import load_games

EXAMPLES = sorted((Path(__file__).parent.parent / "docs" / "examples").glob("*.json"))


def test_there_is_an_example_for_each_game_that_real_models_have_played():
    assert [path.stem for path in EXAMPLES] == ["liars_deck", "poker", "werewolf"]


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda path: path.stem)
def test_example_is_a_whole_match_of_models_from_the_roster(path):
    saved = json.loads(path.read_text(encoding="utf-8"))
    events = [Event(**event) for event in saved["events"]]
    plugin = load_games()[saved["game"]]

    assert path.stem == saved["game"]
    assert saved["status"] == "finished"
    assert (events[0].type, events[-1].type) == ("match_started", "match_finished")
    assert events[0].data["seed"] == saved["seed"]
    # Every seat is a model of the roster, and every seat has a place and a price.
    players = events[0].data["players"]
    assert list(saved["seats"]) == players
    assert set(saved["seats"].values()) <= set(load_config().models)
    assert sorted(Placement(**p).player for p in saved["placements"]) == sorted(players)
    assert set(saved["cost_micro_eur"]) <= set(players)
    assert 0 < sum(saved["cost_micro_eur"].values()) < 500_000  # under the cap of a match
    # A match of an older version of the game is still an example, but cannot be replayed.
    if saved["version"] == plugin.version:
        assert replay(plugin, events) is not None


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda path: path.stem)
def test_example_keeps_thoughts_from_players_and_holds_no_key_or_local_path(path):
    text = path.read_text(encoding="utf-8")
    events = json.loads(text)["events"]

    thoughts = [event for event in events if event["type"] == "thought"]
    assert thoughts
    assert all(event["visible_to"] == [] for event in thoughts)
    assert not re.search(r"sk-or-|sk-[A-Za-z0-9_-]{20,}|api[_-]?key|Bearer ", text)
    assert not re.search(r"[A-Za-z]:\\\\|/Users/|/home/|AppData", text)
