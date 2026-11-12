"""Random events of Throne of Tokens: plague, drought, rebellion, barbarians, gold, harvests.

Each event in ``data/events/`` has a chance per round and a target (a city, a
region around a city, a nation, a free tile of the map). ``roll`` is the last step
of a round (``turn.py``): every event, in id order, draws from its own random
stream, so adding an event never changes when the others strike.

Like the other systems, an event carries its outcome (the new population, the
resources granted, the drought's area and end) and only ``APPLIERS`` change the
state. Who learns of it: the nations it touches. Barbarians appear for spectators
only; nations see them through the fog, like any army.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from arena.engine.plugin import TurnContext
from games.civ.data_loader import CivData, Event
from games.civ.state import NEUTRAL, Army, CivState, Condition, Troop
from games.civ.world import distance


def roll(state: CivState, data: CivData, ctx: TurnContext) -> None:
    """The events step: each event strikes with its chance, on a target drawn from its stream."""
    for event_id in sorted(data.events):
        event = data.events[event_id]
        rng = ctx.rng("event", event_id, state.round)
        if rng.random() >= event.probability_per_round:
            continue
        strike(state, data, ctx, event, rng)


def strike(state: CivState, data: CivData, ctx: TurnContext, event: Event, rng) -> bool:
    """Let one event happen now, on a target drawn from `rng`. False if it has no target.

    Also the way in for a spectator who triggers an event by hand (God mode).
    """
    if event.target == "city":
        cities = _cities_for(state, event)
        if not cities:
            return False
        _at_city(state, ctx, event, rng.choice(cities).id)
    elif event.target == "region":
        cities = [city for city in state.cities if city.owner != NEUTRAL]
        if not cities:
            return False
        centre = rng.choice(cities)
        radius = event.region_radius or 0
        touched = sorted(
            {
                c.owner
                for c in state.cities
                if c.owner != NEUTRAL and distance(c.tile, centre.tile) <= radius
            }
        )
        ctx.emit(
            "random_event",
            {
                "event": event.id,
                "round": state.round,
                "condition": {
                    "col": centre.col,
                    "row": centre.row,
                    "radius": radius,
                    # The events step runs after this round's production: the
                    # drought holds for the next `duration_rounds` productions.
                    "until_round": state.round + event.duration_rounds,
                    "modifiers": dict(event.effects.yield_modifiers),
                },
            },
            visible_to=touched,
        )
    elif event.target == "nation":
        nation = rng.choice(sorted(state.nations))
        _grant(ctx, state, event, nation, None)
    elif event.target == "map":
        return _barbarians(state, data, ctx, event, rng)
    return True


def _cities_for(state: CivState, event: Event) -> list:
    cities = [city for city in state.cities if city.owner != NEUTRAL]
    if event.only_conquered_within_rounds is not None:
        window = event.only_conquered_within_rounds
        cities = [
            c
            for c in cities
            if c.conquered_round is not None and state.round - c.conquered_round <= window
        ]
    return cities


def _at_city(state: CivState, ctx: TurnContext, event: Event, city_id: str) -> None:
    city = state.city(city_id)
    effects = event.effects
    if effects.city_becomes_neutral:
        ctx.emit(
            "random_event",
            {
                "event": event.id,
                "round": state.round,
                "city": city_id,
                "owner": NEUTRAL,
                "from": city.owner,
            },
            visible_to=[city.owner],
        )
        return
    if effects.resources:
        _grant(ctx, state, event, city.owner, city_id)
        return
    population = max(1, city.population + effects.population_change)  # nobody empties a city
    ctx.emit(
        "random_event",
        {"event": event.id, "round": state.round, "city": city_id, "population": population},
        visible_to=[city.owner],
    )


def _grant(
    ctx: TurnContext, state: CivState, event: Event, nation: str, city_id: str | None
) -> None:
    data: dict[str, Any] = {
        "event": event.id,
        "round": state.round,
        "nation": nation,
        "resources": dict(event.effects.resources),
    }
    if city_id is not None:
        data["city"] = city_id
    ctx.emit("random_event", data, visible_to=[nation])


def _barbarians(state: CivState, data: CivData, ctx: TurnContext, event: Event, rng) -> bool:
    taken = {city.tile for city in state.cities} | {army.tile for army in state.armies}
    free = [
        (col, row)
        for row, line in enumerate(state.world.rows)
        for col, terrain in enumerate(line)
        if data.terrain[terrain].movement_cost is not None and (col, row) not in taken
    ]
    if not free:
        return False
    col, row = rng.choice(free)
    units = [
        {"kind": group.unit, "bonus": 0}
        for group in event.effects.spawn_neutral_army
        for _ in range(group.count)
    ]
    ctx.emit(
        "random_event",
        {
            "event": event.id,
            "round": state.round,
            "army": {
                "army": f"a{state.armies_raised + 1}",
                "owner": NEUTRAL,
                "col": col,
                "row": row,
                "units": units,
            },
        },
        visible_to=[],
    )
    return True


# --- events -----------------------------------------------------------------


def _random_event(state: CivState, data: dict[str, Any]) -> None:
    if "population" in data:
        state.city(data["city"]).population = data["population"]
    if "owner" in data:
        state.city(data["city"]).owner = data["owner"]
    if "resources" in data:
        stock = state.nations[data["nation"]].stock
        for resource, amount in data["resources"].items():
            stock[resource] += amount
    if "condition" in data:
        state.conditions.append(Condition(event=data["event"], **data["condition"]))
    if "army" in data:
        army = data["army"]
        state.armies_raised += 1
        state.armies.append(
            Army(
                id=army["army"],
                owner=army["owner"],
                col=army["col"],
                row=army["row"],
                units=[Troop(**unit) for unit in army["units"]],
            )
        )


APPLIERS: dict[str, Callable[[CivState, dict[str, Any]], None]] = {"random_event": _random_event}
