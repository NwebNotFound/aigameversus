"""The orders of a round as plain data, checked and carried out with the economy and army rules.

An order is a dict with an ``order`` name and its arguments. This is the shape a model sends in
``submit_orders`` and the random bot makes (docs/civ-interfaces.md has the final say):

    {"order": "build", "city": "c1", "building": "farm"}
    {"order": "demolish", "city": "c1", "building": "farm"}
    {"order": "set_focus", "city": "c1", "focus": "production"}
    {"order": "train", "city": "c1", "unit": "spearman", "count": 2}
    {"order": "disband", "army": "a1"}
    {"order": "split", "army": "a1", "units": ["spearman"]}
    {"order": "merge", "armies": ["a1", "a2"]}
    {"order": "settle", "army": "a2"}
    {"order": "move", "army": "a1", "to": [4, 3]}

City orders run before army orders (``PHASES``); inside a phase, in the order given.
"""

from __future__ import annotations

from typing import Any

from arena.engine.plugin import TurnContext
from games.civ import armies, economy
from games.civ.data_loader import CivData
from games.civ.state import CivState

Order = dict[str, Any]

# order name -> required argument names
FIELDS: dict[str, tuple[str, ...]] = {
    "build": ("city", "building"),
    "demolish": ("city", "building"),
    "set_focus": ("city", "focus"),
    "train": ("city", "unit", "count"),
    "disband": ("army",),
    "split": ("army", "units"),
    "merge": ("armies",),
    "settle": ("army",),
    "move": ("army", "to"),
}
PHASES = (
    ("build", "demolish", "set_focus", "train"),
    ("disband", "split", "merge", "settle", "move"),
)


def sorted_for_the_round(orders: list[Order]) -> list[Order]:
    """City orders first, then army orders; each group keeps the order it was given in."""
    rank = {name: i for i, phase in enumerate(PHASES) for name in phase}
    return sorted(orders, key=lambda order: rank.get(order.get("order"), 99))


def order_problem(state: CivState, data: CivData, player: str, order: Order) -> str | None:
    """None when the order is legal now, else a message for the player."""
    name = order.get("order")
    if name not in FIELDS:
        return f"There is no order '{name}'. Orders: {', '.join(FIELDS)}."
    missing = [field for field in FIELDS[name] if field not in order]
    if missing:
        needs = ", ".join(FIELDS[name])
        return f"The order '{name}' needs: {needs}. Missing: {', '.join(missing)}."
    if name == "build":
        return economy.build_problem(state, data, player, order["city"], order["building"])
    if name == "demolish":
        return economy.demolish_problem(state, player, order["city"], order["building"])
    if name == "set_focus":
        return economy.focus_problem(state, data, player, order["city"], order["focus"])
    if name == "train":
        count = order["count"]
        if not isinstance(count, int) or isinstance(count, bool):
            return f"count must be a whole number, not {count!r}."
        return armies.train_problem(state, data, player, order["city"], order["unit"], count)
    if name == "disband":
        return armies.disband_problem(state, player, order["army"])
    if name == "split":
        units = order["units"]
        if not isinstance(units, list) or not all(isinstance(kind, str) for kind in units):
            return "units must be a list of unit ids, for example ['spearman']."
        return armies.split_problem(state, player, order["army"], units)
    if name == "merge":
        ids = order["armies"]
        if not isinstance(ids, list) or not all(isinstance(i, str) for i in ids):
            return "armies must be a list of army ids, for example ['a1', 'a2']."
        return armies.merge_problem(state, data, player, ids)
    if name == "settle":
        return armies.settle_problem(state, data, player, order["army"])
    tile = order["to"]
    if not (
        isinstance(tile, list | tuple) and len(tile) == 2 and all(type(n) is int for n in tile)
    ):
        return "to must be a tile [col, row], for example [4, 3]."
    return armies.move_problem(state, data, player, order["army"], (tile[0], tile[1]))


def apply_order(
    state: CivState, data: CivData, ctx: TurnContext, player: str, order: Order
) -> None:
    """Carry out a legal order (check it with ``order_problem`` first)."""
    name = order["order"]
    if name == "build":
        economy.build(state, data, ctx, player, order["city"], order["building"])
    elif name == "demolish":
        economy.demolish(state, data, ctx, player, order["city"], order["building"])
    elif name == "set_focus":
        economy.set_focus(state, data, ctx, player, order["city"], order["focus"])
    elif name == "train":
        armies.train(state, data, ctx, player, order["city"], order["unit"], order["count"])
    elif name == "disband":
        armies.disband(state, ctx, player, order["army"])
    elif name == "split":
        armies.split(state, ctx, player, order["army"], order["units"])
    elif name == "merge":
        armies.merge(state, data, ctx, player, order["armies"])
    elif name == "settle":
        armies.settle(state, data, ctx, player, order["army"])
    else:
        col, row = order["to"]
        armies.move(state, data, ctx, player, order["army"], (col, row))
