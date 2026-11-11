"""Rebuilds the state of a match from its event log."""

from collections.abc import Iterable

from pydantic import BaseModel

from arena.engine.plugin import GamePlugin
from arena.engine.types import Event, EventSource


class ReplayError(Exception):
    """The log cannot be replayed with this plugin."""


def replay[StateT: BaseModel](plugin: GamePlugin[StateT], events: Iterable[Event]) -> StateT:
    """Return the game state after `events`.

    Needs no seed and runs no rules: it starts from `initial_state` and applies
    the game events in order. A prefix of a log gives the state at that point.
    """
    events = iter(events)
    start = next(events, None)
    if start is None or start.source is not EventSource.ENGINE or start.type != "match_started":
        raise ReplayError("The log does not start with match_started")
    recorded = (start.data["game"], start.data["version"])
    if recorded != (plugin.id, plugin.version):
        raise ReplayError(
            f"The log was recorded with {recorded[0]} version {recorded[1]}, "
            f"but the plugin is {plugin.id} version {plugin.version}"
        )
    state = plugin.initial_state(start.data["players"], start.data["settings"])
    for event in events:
        if event.source is EventSource.GAME:
            plugin.apply_event(state, event)
    return state
