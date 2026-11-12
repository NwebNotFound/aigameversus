"""The random bot of Throne of Tokens: a few legal random orders, built from the observation only.

    call = random_orders(observation, rng)  # {"orders": [...]} for submit_orders

As docs/civ-interfaces.md says, a random bot never needs the state: it picks from ``legal``
(what each city may build and train) and ``armies[].reachable``, and keeps count of what it
spends so that the orders do not outbid its own stock. It does not attack (it never moves
onto a tile where another nation stands) and does not talk; it answers offers at random.
"""

from __future__ import annotations

import random
from typing import Any

# the chance, per city or army, that the bot gives it an order this round
CITY_BUILD = 0.5
CITY_TRAIN = 0.4
CITY_FOCUS = 0.1
ARMY_MOVE = 0.6
ARMY_SPLIT = 0.1
ARMY_DISBAND = 0.02
FOCUSES = ("growth", "production", "military")


def random_orders(observation: dict[str, Any], rng: random.Random) -> dict[str, Any]:
    """A `submit_orders` call: city orders, army orders, then answers to offers."""
    stock = dict(observation["stock"])
    orders: list[dict[str, Any]] = []
    legal = observation["legal"]

    def pay(cost: dict[str, int]) -> bool:
        if any(stock.get(resource, 0) < amount for resource, amount in cost.items()):
            return False
        for resource, amount in cost.items():
            stock[resource] -= amount
        return True

    for city in observation["cities"]:
        options = legal["cities"].get(city["id"], {"build": {}, "train": {}})
        if rng.random() < CITY_FOCUS:
            orders.append({"type": "focus", "city": city["id"], "focus": rng.choice(FOCUSES)})
        if rng.random() < CITY_BUILD and city["slots_free"] > 0:
            for building in rng.sample(sorted(options["build"]), len(options["build"])):
                if pay(options["build"][building]):
                    orders.append({"type": "build", "city": city["id"], "building": building})
                    break
        if rng.random() < CITY_TRAIN:
            for unit in rng.sample(sorted(options["train"]), len(options["train"])):
                count = rng.randint(1, options["train"][unit])
                cost = {r: n * count for r, n in legal["unit_cost"][unit].items()}
                if pay(cost):
                    orders.append(
                        {"type": "train", "city": city["id"], "unit": unit, "count": count}
                    )
                    break

    taken = {tuple(c["tile"]) for c in observation["seen"]["cities"]}
    taken |= {tuple(a["tile"]) for a in observation["seen"]["armies"]}
    for army in observation["armies"]:
        if army["can_settle"]:
            orders.append({"type": "settle", "army": army["id"]})
            continue
        roll = rng.random()
        if roll < ARMY_DISBAND:
            orders.append({"type": "disband", "army": army["id"]})
        elif roll < ARMY_DISBAND + ARMY_SPLIT and sum(army["units"].values()) > 1:
            kinds = [kind for kind, n in sorted(army["units"].items()) for _ in range(n)]
            orders.append({"type": "split", "army": army["id"], "units": [rng.choice(kinds)]})
        elif roll < ARMY_DISBAND + ARMY_SPLIT + ARMY_MOVE:
            free = [t for t in army["reachable"] if tuple(t) not in taken]
            if free:
                orders.append({"type": "move", "army": army["id"], "to": rng.choice(free)})

    for offer in observation["offers"]:
        orders.append({"type": "respond", "offer": offer["id"], "accept": rng.random() < 0.5})
    return {"orders": orders}
