"""Rebuilds the state of a match from its event log."""

from collections.abc import Iterable

from pydantic import BaseModel

from arena.engine.plugin import GamePlugin
from arena.engine.types import Event, EventSource, game_settings


class ReplayError(Exception):
    """The log cannot be replayed with this plugin."""


def recorded_version(start: Event) -> str:
    """The rules version a log was recorded with; a log from before the field is "1"."""
    return str(start.data.get("version", "1"))


def plugin_for[StateT: BaseModel](plugin: GamePlugin[StateT], start: Event) -> GamePlugin[StateT]:
    """The plugin with the rules this log was recorded with (its `match_started`)."""
    game, version = start.data["game"], recorded_version(start)
    if game != plugin.id:
        raise ReplayError(f"The log was recorded with {game}, but the plugin is {plugin.id}")
    try:
        return plugin.at_version(version)
    except ValueError as missing:
        raise ReplayError(
            f"The log was recorded with {game} version {version}, "
            f"but the plugin is {plugin.id} version {plugin.version}"
        ) from missing


def replay[StateT: BaseModel](plugin: GamePlugin[StateT], events: Iterable[Event]) -> StateT:
    """Return the game state after `events`.

    Needs no seed and runs no rules: it starts from `initial_state` and applies
    the game events in order. A prefix of a log gives the state at that point.
    """
    events = iter(events)
    start = next(events, None)
    if start is None or start.source is not EventSource.ENGINE or start.type != "match_started":
        raise ReplayError("The log does not start with match_started")
    plugin = plugin_for(plugin, start)
    state = plugin.initial_state(start.data["players"], game_settings(start.data["settings"]))
    for event in events:
        if event.source is EventSource.GAME:
            plugin.apply_event(state, event)
    return state
