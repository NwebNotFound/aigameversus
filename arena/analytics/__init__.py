"""Analytics of one match for the spectator UI: per move, per player and per round.

`match_analytics(game, events, spoilers)` is a pure function of the stored log, so it
works the same for a running match (the log so far), a finished one and a replay
file. Without spoilers it reads only public events: what a player hid (cards,
roles, thoughts) never reaches a spoiler-free viewer, and numbers that need it are
null. `docs/METRICS.md` defines every number.
"""

from collections.abc import Callable, Iterable, Mapping
from typing import Any

from arena.analytics import liars_deck
from arena.analytics.situation import BUILDERS as SITUATIONS
from arena.analytics.situation import situation
from arena.engine.types import Event
from arena.transcript.common import public_settings

# Each analyzer takes (seq, event) pairs: seq is the event's position in the whole log,
# so the UI can jump a replay to a move even when some events are filtered out.
ANALYZERS: dict[str, Callable[[list[tuple[int, Event]], bool], dict[str, Any]]] = {
    "liars_deck": liars_deck.analyze,
}


class NoAnalytics(ValueError):
    """The game has no analytics yet."""


def match_analytics(
    game: str, events: Iterable[Event], spoilers: bool, names: Mapping[str, str] | None = None
) -> dict[str, Any]:
    """The analytics of a match. `names` maps seats to the names its sentences use.

    A game with a situation but no analyzer yet answers with the situation only.
    """
    analyze = ANALYZERS.get(game)
    if analyze is None and game not in SITUATIONS:
        known = sorted({*ANALYZERS, *SITUATIONS})
        raise NoAnalytics(f"No analytics for {game} yet (known: {', '.join(known)})")
    log = list(enumerate(events))
    if not spoilers:
        # The start of the match stays, as in the transcript: without the seed (it would
        # give every hidden draw away) and with only the settings anyone may read.
        log = [
            (seq, _public_start(e))
            for seq, e in log
            if e.visible_to is None or e.type == "match_started"
        ]
    numbers = analyze(log, spoilers) if analyze else {"meta": {}}
    result = {
        "game": game,
        "spoilers": spoilers,
        "events": len(log),
        "situation": situation(game, log, spoilers, names or {}),
        **numbers,
    }
    # Which parts this answer has, so a client checks one list instead of probing keys:
    # Poker answers with ["situation"] only, Liar's Deck with its moves, totals and more.
    result["sections"] = [key for key in result if key not in _HEAD]
    # False: a situation only, no numbers yet for this game (Poker today).
    result["numbers"] = result["sections"] != ["situation"]
    return result


_HEAD = {"game", "spoilers", "events", "meta", "sections", "numbers"}


def _public_start(event: Event) -> Event:
    if event.type != "match_started":
        return event
    data = {k: v for k, v in event.data.items() if k != "seed"}
    data["settings"] = public_settings(event.data.get("settings") or {})
    return event.model_copy(update={"data": data})
