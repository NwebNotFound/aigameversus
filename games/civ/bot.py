"""The random bot of Throne of Tokens: valid random orders, never a rejected one.

    orders = random_orders(state, data, player, rng)

It plays on a copy of the state and carries out each order it picks, so a later order is legal
after the earlier ones (the stock is spent, a new army exists). Combat, diplomacy and events
are not its business; it only fills the order form.
"""

from __future__ import annotations

import random
from collections.abc import Callable

from arena.engine.plugin import TurnContext
from arena.engine.rng import derive_rng
from games.civ import armies as army_rules
from games.civ.data_loader import CivData
from games.civ.orders import Order, apply_order, order_problem
from games.civ.state import CivState
from games.civ.turn import apply_event

# the chance, per city or army, that the bot gives it an order this round
CITY_BUILD = 0.5
CITY_TRAIN = 0.4
CITY_FOCUS = 0.1
ARMY_MOVE = 0.6
ARMY_SPLIT = 0.1
ARMY_DISBAND = 0.02


def random_orders(state: CivState, data: CivData, player: str, rng: random.Random) -> list[Order]:
    """Legal random orders for this nation: city orders first, then army orders."""
    scratch = state.model_copy(deep=True)
    ctx = TurnContext(
        lambda *key: derive_rng(rng.getrandbits(32), "civ-bot", *key),
        lambda event: apply_event(scratch, event),
    )
    chosen: list[Order] = []

    def take(order: Order) -> bool:
        if order_problem(scratch, data, player, order) is not None:
            return False
        apply_order(scratch, data, ctx, player, order)
        chosen.append(order)
        return True

    for city in [c for c in scratch.cities if c.owner == player]:
        if rng.random() < CITY_FOCUS:
            focus = rng.choice(sorted(data.balance.city.focus_yields))
            take({"order": "set_focus", "city": city.id, "focus": focus})
        if rng.random() < CITY_BUILD:
            builds = [
                {"order": "build", "city": city.id, "building": b} for b in sorted(data.buildings)
            ]
            _take_one(rng, builds, take)
        if rng.random() < CITY_TRAIN:
            units = sorted(u for u in data.units if data.units[u].strength > 0)
            trains = [
                {"order": "train", "city": city.id, "unit": u, "count": rng.randint(1, 3)}
                for u in units
            ]
            _take_one(rng, trains, take)

    for army in [a for a in scratch.armies if a.owner == player]:
        if army.id not in {a.id for a in scratch.armies}:  # merged or disbanded earlier
            continue
        if take({"order": "settle", "army": army.id}):
            continue
        roll = rng.random()
        if roll < ARMY_DISBAND:
            take({"order": "disband", "army": army.id})
        elif roll < ARMY_DISBAND + ARMY_SPLIT and len(army.units) > 1:
            kinds = [troop.kind for troop in army.units]
            take({"order": "split", "army": army.id, "units": [rng.choice(kinds)]})
        elif roll < ARMY_DISBAND + ARMY_SPLIT + ARMY_MOVE:
            ways = army_rules.reachable(scratch, data, army.id)
            if ways and scratch.army(army.id).moved_in_round != scratch.round:
                col, row = rng.choice(sorted(ways))
                take({"order": "move", "army": army.id, "to": [col, row]})
    return chosen


def _take_one(rng: random.Random, options: list[Order], take: Callable[[Order], bool]) -> None:
    rng.shuffle(options)
    for option in options:
        if take(option):
            return
