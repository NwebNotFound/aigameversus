"""A round of Throne of Tokens, as far as it is built, and the one way the state changes.

The steps of a round, in the order they must run:

    begin_round(state, ctx)
    economy.finish_construction(state, ctx)
    # orders for cities: economy.build, demolish, set_focus; armies.train
    # orders that organise armies: armies.disband, split, merge, settle
    # then, once per army: armies.move
    economy.produce(state, data, ctx)
    armies.starve(state, data, ctx)
    economy.grow(state, data, ctx)

Armies are organised before any of them moves, so that no unit walks twice in
a round as part of two armies.
"""

from __future__ import annotations

from typing import Any

from arena.engine.plugin import TurnContext
from arena.engine.types import Event
from games.civ import armies, economy
from games.civ.state import CivState


def begin_round(state: CivState, ctx: TurnContext) -> None:
    ctx.emit("round_started", {"round": state.round + 1})


def apply_event(state: CivState, event: Event) -> None:
    """Apply one game event to the state. Nothing else changes it."""
    _APPLY[event.type](state, event.data)


def _round_started(state: CivState, data: dict[str, Any]) -> None:
    state.round = data["round"]


_APPLY = {"round_started": _round_started, **economy.APPLIERS, **armies.APPLIERS}
