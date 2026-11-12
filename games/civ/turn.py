"""A round of Throne of Tokens, as far as it is built, and the one way the state changes.

The steps of a round, in the order they must run:

    begin_round(state, ctx)
    diplomacy.expire(state, ctx)
    economy.finish_construction(state, ctx)
    # orders, in this order:
    #   diplomacy: diplomacy.message, propose_treaty, respond_treaty, propose_trade,
    #              respond_trade, declare_war, break_treaty
    #   cities:    economy.build, demolish, set_focus; armies.train
    #   armies:    armies.disband, split, merge, settle, move; combat.attack, fortify, pillage
    combat.resolve(state, data, ctx)  # every attack of the round is fought
    diplomacy.settle(state, data, ctx)  # the trade step: tributes and agreed trades
    economy.produce(state, data, ctx)
    armies.starve(state, data, ctx)
    economy.grow(state, data, ctx)
    events.roll(state, data, ctx)  # random events
    combat.weariness(state, data, ctx)  # rounds at war cost production
    victory.check(state, data, ctx)  # the match may be won

The round number is what "once per round" is counted against: an army
remembers the round of its last move.
"""

from __future__ import annotations

from typing import Any

from arena.engine.plugin import TurnContext
from arena.engine.types import Event
from games.civ import armies, combat, diplomacy, economy, events, victory
from games.civ.state import CivState


def begin_round(state: CivState, ctx: TurnContext) -> None:
    ctx.emit("round_started", {"round": state.round + 1})


def apply_event(state: CivState, event: Event) -> None:
    """Apply one game event to the state. Nothing else changes it."""
    _APPLY[event.type](state, event.data)


def _round_started(state: CivState, data: dict[str, Any]) -> None:
    state.round = data["round"]


_APPLY = {
    "round_started": _round_started,
    **economy.APPLIERS,
    **armies.APPLIERS,
    **diplomacy.APPLIERS,
    **combat.APPLIERS,
    **events.APPLIERS,
    **victory.APPLIERS,
}
