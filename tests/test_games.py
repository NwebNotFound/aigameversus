import asyncio
from pathlib import Path

import pytest

import games
from arena.agents.random_bot import random_bots
from arena.engine.match import Match
from arena.engine.plugin import GamePlugin
from arena.engine.replay import replay
from arena.games import load_games

COUNTER = """
from tests.engine.counter_game import SequentialCounter


class Plugin(SequentialCounter):
    id = "{id}"
"""


def test_every_game_folder_with_a_plugin_is_found_by_its_folder_name():
    found = load_games()

    folders = sorted(path.parent.name for path in Path(games.__path__[0]).glob("*/plugin.py"))
    assert list(found) == folders
    assert "toy" in found
    for game_id, plugin in found.items():
        assert isinstance(plugin, GamePlugin)
        assert plugin.id == game_id
        # What a model needs to play it is there too.
        assert plugin.name and plugin.rules()


def test_folder_without_a_plugin_module_is_not_a_game_yet(fake_games):
    fake_games(alpha=COUNTER.format(id="alpha"), data_only=None, beta=COUNTER.format(id="beta"))

    found = load_games()

    # The counter class that the plugin modules import is not taken for a game of its own.
    assert list(found) == ["alpha", "beta"]
    assert found["alpha"].name == "Counter"


@pytest.mark.parametrize(
    ("source", "problem"),
    [
        (COUNTER.format(id="other"), "plugin id 'other' must be the folder name 'broken'"),
        (COUNTER.format(id="broken") + COUNTER.format(id="broken").replace("Plugin", "Twin"), "2"),
        ("VALUE = 1\n", "exactly one GamePlugin, found 0"),
    ],
    ids=["id is not the folder name", "two plugins", "no plugin"],
)
def test_folder_that_breaks_the_naming_rule_stops_the_start(fake_games, source, problem):
    fake_games(broken=source)

    with pytest.raises(RuntimeError, match=f"games.broken.plugin.*{problem}"):
        load_games()


def reordered(value):
    """The same JSON data with the keys of every object in the opposite order."""
    if isinstance(value, dict):
        return {key: reordered(item) for key, item in reversed(value.items())}
    if isinstance(value, list):
        return [reordered(item) for item in value]
    return value


@pytest.mark.parametrize("game_id", list(load_games()))
def test_every_game_plays_a_bot_match_that_replays_whatever_the_order_of_keys(game_id):
    plugin = load_games()[game_id]
    players = [f"p{seat}" for seat in range(1, plugin.min_players + 1)]
    match = Match(plugin, random_bots(plugin, players, 3), seed=3)

    asyncio.run(match.run())

    assert match.events[-1].type == "match_finished"
    assert replay(plugin, match.events) == match.state
    # Postgres stores a JSON object without the order of its keys, so a game
    # must not read anything from that order.
    stored = [event.model_copy(update={"data": reordered(event.data)}) for event in match.events]
    assert stored == match.events
    assert replay(plugin, stored) == match.state
