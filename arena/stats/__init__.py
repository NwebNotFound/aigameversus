"""Per-game statistics computed from the event log of a match.

Every game with statistics has a module here with the same shape: `match_stats`
turns the log of one match into one Pydantic model per player, `aggregate` adds
many matches of one player up. `STATS` finds them by game id.
"""

from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Any, NamedTuple

from arena.engine.types import Event, PlayerId
from arena.stats import liars_deck, poker, werewolf


class GameStats(NamedTuple):
    match_stats: Callable[[Iterable[Event]], Mapping[PlayerId, Any]]
    aggregate: Callable[[Sequence[Any]], Any]


STATS: dict[str, GameStats] = {
    "liars_deck": GameStats(liars_deck.match_stats, liars_deck.aggregate),
    "poker": GameStats(poker.match_stats, poker.aggregate),
    "werewolf": GameStats(werewolf.match_stats, werewolf.aggregate),
}
