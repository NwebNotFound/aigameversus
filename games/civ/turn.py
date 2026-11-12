"""A round of Throne of Tokens, and the one way the state changes.

The steps of a round, in the order they must run (docs/civ-interfaces.md):

    open_round(state, data, ctx):
        begin_round(state, ctx)
        diplomacy.expire(state, ctx)
        economy.finish_construction(state, ctx)
    # every nation answers with one submit_orders call, on this state
    close_round(state, data, ctx, orders):
        orders.run(state, data, ctx, orders)  # diplomacy, then cities, then armies
        neutrals.act(state, data, ctx)  # barbarians attack or walk towards a city
        combat.resolve(state, data, ctx)  # every attack of the round is fought
        diplomacy.settle(state, data, ctx)  # the trade step: tributes and agreed trades
        economy.produce(state, data, ctx)
        armies.starve(state, data, ctx)
        economy.grow(state, data, ctx)
        events.roll(state, data, ctx)  # random events
        combat.weariness(state, data, ctx)  # rounds at war cost production
        victory.check(state, data, ctx)  # the match may be won

The plugin opens a round, asks every nation, then closes it and opens the next,
so a nation is always asked on an open round. The round number is what "once
per round" is counted against: an army remembers the round of its last move.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from arena.engine.plugin import TurnContext
from arena.engine.types import Event
from games.civ import armies, combat, diplomacy, economy, events, neutrals, orders, victory
from games.civ.data_loader import CivData
from games.civ.state import CivState
from games.civ.world import Start, WorldMap


def begin_round(state: CivState, ctx: TurnContext) -> None:
    ctx.emit("round_started", {"round": state.round + 1})


def open_round(state: CivState, data: CivData, ctx: TurnContext) -> None:
    begin_round(state, ctx)
    diplomacy.expire(state, ctx)
    economy.finish_construction(state, ctx)


def close_round(
    state: CivState,
    data: CivData,
    ctx: TurnContext,
    given: Mapping[str, Sequence[Mapping[str, Any]]],
) -> None:
    orders.run(state, data, ctx, given)
    neutrals.act(state, data, ctx)
    combat.resolve(state, data, ctx)
    diplomacy.settle(state, data, ctx)
    economy.produce(state, data, ctx)
    armies.starve(state, data, ctx)
    economy.grow(state, data, ctx)
    events.roll(state, data, ctx)
    combat.weariness(state, data, ctx)
    victory.check(state, data, ctx)


def apply_event(state: CivState, event: Event) -> None:
    """Apply one game event to the state. Nothing else changes it."""
    _APPLY[event.type](state, event.data)


def _round_started(state: CivState, data: dict[str, Any]) -> None:
    state.round = data["round"]
    # What the board and the observation show of the round before stays one round.
    state.refused = [r for r in state.refused if r["round"] >= state.round - 1]
    state.battles = [b for b in state.battles if b["round"] >= state.round - 1]


def _map_drawn(state: CivState, data: dict[str, Any]) -> None:
    state.world = WorldMap(
        rows=[list(row) for row in data["rows"]],
        starts=[Start(**start) for start in data["starts"]],
    )


def _order_refused(state: CivState, data: dict[str, Any]) -> None:
    state.refused.append(dict(data))


def _plan_set(state: CivState, data: dict[str, Any]) -> None:
    state.nations[data["nation"]].plan = data["plan"]


_APPLY = {
    "round_started": _round_started,
    "map_drawn": _map_drawn,
    "order_refused": _order_refused,
    "plan_set": _plan_set,
    **economy.APPLIERS,
    **armies.APPLIERS,
    **diplomacy.APPLIERS,
    **combat.APPLIERS,
    **events.APPLIERS,
    **victory.APPLIERS,
}
