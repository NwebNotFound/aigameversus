"""The economy of Throne of Tokens: cities, what they yield, buildings, upkeep and growth.

Every function that changes something does it by emitting an event, private to
the nation it concerns; the functions in ``APPLIERS`` are the only code here
that touches the state. Its part of a round (``turn.py`` has the whole order):

    finish_construction(state, ctx)  # sites from earlier rounds become buildings
    if (problem := build_problem(state, data, "ada", "c1", "farm")) is None:
        build(state, data, ctx, "ada", "c1", "farm")  # also: demolish, set_focus
    produce(state, data, ctx)  # yields in, population and units fed
    grow(state, data, ctx)  # cities with enough surplus food gain population

All numbers come from ``data/balance.yaml`` (``city``, ``army``),
``data/buildings.yaml``, ``data/terrain.yaml`` and ``data/units.yaml``.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable, Mapping
from decimal import Decimal
from typing import Any, get_args

from arena.engine.plugin import TurnContext
from games.civ.data_loader import CivData, Resource
from games.civ.state import City, CivState, Site, Stock
from games.civ.world import Hex, distance

RESOURCES: tuple[Resource, ...] = get_args(Resource)


# --- what a city is worth ---------------------------------------------------


def worked_tiles(state: CivState, data: CivData, city_id: str) -> list[Hex]:
    """The tiles this city works: those in its radius that no other city is nearer to.

    A tile feeds one city only. Of two cities equally near, the older one works
    it. A tile with a city on it is worked by nobody.
    """
    reach = {city.id: _work_radius(data, city) for city in state.cities}
    occupied = {city.tile for city in state.cities}

    def worker(tile: Hex) -> str:
        near = [city for city in state.cities if distance(city.tile, tile) <= reach[city.id]]
        # min() keeps the first of equals, and cities are in founding order.
        return min(near, key=lambda city: distance(city.tile, tile)).id

    around = state.world.within(state.city(city_id).tile, reach[city_id])
    return [tile for tile in around if tile not in occupied and worker(tile) == city_id]


def city_yields(state: CivState, data: CivData, city_id: str) -> Stock:
    """What the city makes in a round, before its population eats.

    The city itself, its worked tiles, one of the focus resource per
    population, and its finished buildings.
    """
    city, rules = state.city(city_id), data.balance.city
    total = _amounts(rules.base_yields)
    for tile in worked_tiles(state, data, city_id):
        _add(total, data.terrain[state.world.terrain(tile)].yields)
    total[rules.focus_yields[city.focus]] += city.population
    for building in city.buildings:
        _add(total, data.buildings[building].effects.yields)
    return total


def building_slots(data: CivData, population: int) -> int:
    slots = data.balance.city.building_slots
    return min(slots.base + population // slots.population_divisor, slots.max)


def city_viewpoints(state: CivState, data: CivData, player: str) -> list[tuple[Hex, int]]:
    """Where the nation's cities stand and how far each sees, for ``fog.visible_tiles``."""
    sight = data.balance.map.fog_vision_radius
    return [
        (city.tile, sight + sum(data.buildings[b].effects.vision_bonus for b in city.buildings))
        for city in state.cities
        if city.owner == player
    ]


def _work_radius(data: CivData, city: City) -> int:
    rules = data.balance.city
    grown = city.population >= rules.expanded_at_population
    return rules.expanded_work_radius if grown else rules.work_radius


# --- orders -----------------------------------------------------------------
# A `*_problem` function returns None when the order is legal, otherwise a
# message that tells the player how to fix it. The order itself must be legal.


def found_city(state: CivState, ctx: TurnContext, owner: str, tile: Hex) -> str:
    """Put a new city on the tile and return its id. Where a city may stand is the caller's rule."""
    city_id = f"c{len(state.cities) + 1}"
    col, row = tile
    ctx.emit(
        "city_founded",
        {"city": city_id, "owner": owner, "col": col, "row": row},
        visible_to=[owner],
    )
    return city_id


def build_problem(
    state: CivState, data: CivData, player: str, city_id: str, building_id: str
) -> str | None:
    if problem := not_their_city(state, player, city_id):
        return problem
    building = data.buildings.get(building_id)
    if building is None:
        return f"There is no building '{building_id}'. Buildings: {', '.join(data.buildings)}."
    city = state.city(city_id)
    planned = city.buildings + [site.building for site in city.sites]
    if planned.count(building_id) >= building.max_per_city:
        return (
            f"{city_id} already has a {building_id}, built or under construction "
            f"(at most {building.max_per_city} per city)."
        )
    slots = building_slots(data, city.population)
    if len(planned) >= slots:
        return (
            f"{city_id} has no free building slot: {len(planned)} of {slots} are taken at "
            f"population {city.population}. Demolish a building or let the city grow."
        )
    needs = building.requires_adjacent_terrain
    beside = [tile for tile in state.world.within(city.tile, 1) if tile != city.tile]
    if needs and not any(state.world.terrain(tile) in needs for tile in beside):
        return f"A {building_id} needs {' or '.join(needs)} next to the city; {city_id} has none."
    return cannot_pay(state.nations[player].stock, building.cost, f"A {building_id} costs")


def build(
    state: CivState, data: CivData, ctx: TurnContext, player: str, city_id: str, building_id: str
) -> None:
    """Pay for a building and start it. It takes a slot now and works once it is finished."""
    must_be_legal(build_problem(state, data, player, city_id, building_id))
    ctx.emit(
        "building_started",
        {
            "city": city_id,
            "building": building_id,
            "cost": dict(data.buildings[building_id].cost),
            "rounds": data.building_rules.build_rounds,
        },
        visible_to=[player],
    )


def demolish_problem(state: CivState, player: str, city_id: str, building_id: str) -> str | None:
    if problem := not_their_city(state, player, city_id):
        return problem
    standing = state.city(city_id).buildings
    if building_id not in standing:
        return (
            f"{city_id} has no finished {building_id}. "
            f"Its buildings: {', '.join(standing) or 'none'}."
        )
    return None


def demolish(
    state: CivState, data: CivData, ctx: TurnContext, player: str, city_id: str, building_id: str
) -> None:
    """Tear a finished building down for a share of its cost. The slot is free at once."""
    must_be_legal(demolish_problem(state, player, city_id, building_id))
    share = Decimal(str(data.building_rules.demolish_refund))
    cost = data.buildings[building_id].cost
    refund = {resource: int(amount * share) for resource, amount in cost.items()}  # rounded down
    ctx.emit(
        "building_demolished",
        {"city": city_id, "building": building_id, "refund": refund},
        visible_to=[player],
    )


def focus_problem(
    state: CivState, data: CivData, player: str, city_id: str, focus: str
) -> str | None:
    if problem := not_their_city(state, player, city_id):
        return problem
    choices = list(data.balance.city.focus_yields)
    if focus not in choices:
        return f"There is no focus '{focus}'. Choose one of: {', '.join(choices)}."
    return None


def set_focus(
    state: CivState, data: CivData, ctx: TurnContext, player: str, city_id: str, focus: str
) -> None:
    """Choose which resource the city's population adds, from this round's production on."""
    must_be_legal(focus_problem(state, data, player, city_id, focus))
    ctx.emit("city_focus_set", {"city": city_id, "focus": focus}, visible_to=[player])


def not_their_city(state: CivState, player: str, city_id: str) -> str | None:
    own = [city.id for city in state.cities if city.owner == player]
    if city_id in own:
        return None
    # The same answer for a city of another nation: its existence stays hidden.
    return f"You have no city '{city_id}'. Your cities: {', '.join(own) or 'none'}."


def cannot_pay(stock: Stock, cost: Mapping[Resource, int], what: str) -> str | None:
    """None if the stock covers the cost, otherwise "`what` 4 wood, 3 gold; you have ..."."""
    if all(stock[resource] >= amount for resource, amount in cost.items()):
        return None
    have = {resource: stock[resource] for resource in cost}
    return f"{what} {_text(cost)}; you have {_text(have)}."


def must_be_legal(problem: str | None) -> None:
    if problem is not None:
        raise ValueError(problem)


# --- the steps of a round ---------------------------------------------------


def finish_construction(state: CivState, ctx: TurnContext) -> None:
    """Turn sites whose time is up into buildings and bring the others a round closer."""
    for city in state.cities:
        for site in list(city.sites):
            if site.rounds_left <= 1:
                ctx.emit(
                    "building_completed",
                    {"city": city.id, "building": site.building},
                    visible_to=[city.owner],
                )
        if city.sites:
            ctx.emit("construction_progressed", {"city": city.id}, visible_to=[city.owner])


def upkeep(data: CivData, units: Iterable[str]) -> dict[Resource, int]:
    """What units of these kinds cost per round."""
    due = _amounts({})
    for unit in units:
        _add(due, data.units[unit].upkeep)
    return {resource: amount for resource, amount in due.items() if amount}


def weary_modifier(data: CivData, rounds: int) -> float:
    """What so many rounds in a row at war take off production (≤ 0)."""
    rules = data.balance.war_weariness
    return max(rules.production_modifier_per_round * rounds, rules.max_production_modifier)


def production_modifier(state: CivState, data: CivData, nation: str) -> float:
    """What war weariness and a lost capital take off a nation's yields (≤ 0)."""
    kept = state.nations[nation]
    modifier = weary_modifier(data, kept.weary_rounds)
    if kept.capital_lost_until is not None and state.round <= kept.capital_lost_until:
        modifier += data.balance.conquest.capital_lost_production_modifier
    return max(modifier, -1.0)


def produce(state: CivState, data: CivData, ctx: TurnContext) -> None:
    """The production step: every nation takes in its yields and feeds population and units.

    Yields go to the nation's stock. The population eats first, then the
    units take their upkeep; what the stock cannot cover is not paid. A round
    in which upkeep was not paid in full counts as hungry
    (``units_lost_to_hunger``).

    The food a city makes beyond what its own population eats also counts
    towards that city's growth. War weariness and a lost capital take their share of the
    yields first (`production_modifier`), rounded down.
    """
    hunger = data.balance.city.food_per_population
    for player, nation in state.nations.items():
        cities = [city for city in state.cities if city.owner == player]
        due = upkeep(data, state.units_of(player))
        if not cities and not due and not nation.hungry_rounds:
            continue
        yields, stored = _amounts({}), {}
        for city in cities:
            made = city_yields(state, data, city.id)
            _add(yields, made)
            if made["food"] > city.population * hunger:
                stored[city.id] = made["food"] - city.population * hunger
        modifier = production_modifier(state, data, player)
        if modifier:
            yields = {r: math.floor(n * (1 + modifier)) for r, n in yields.items()}
        eaten = sum(city.population for city in cities) * hunger
        stock = {resource: nation.stock[resource] + yields[resource] for resource in RESOURCES}
        stock["food"] = max(stock["food"] - eaten, 0)
        paid_in_full = all(stock[resource] >= amount for resource, amount in due.items())
        for resource, amount in due.items():
            stock[resource] = max(stock[resource] - amount, 0)
        ctx.emit(
            "production",
            {
                "player": player,
                "yields": yields,
                "eaten": eaten,
                "upkeep": due,
                "stock": stock,
                "hungry_rounds": 0 if paid_in_full else nation.hungry_rounds + 1,
                "stored": stored,
            },
            visible_to=[player],
        )


def units_lost_to_hunger(state: CivState, data: CivData, player: str) -> int:
    """How many units the nation loses this round because upkeep went unpaid.

    None while the hungry rounds are covered by a granary. Only the nation's
    best granary counts; several do not add up.
    """
    covered = max(
        (
            data.buildings[building].effects.famine_delay_rounds
            for city in state.cities
            if city.owner == player
            for building in city.buildings
        ),
        default=0,
    )
    if state.nations[player].hungry_rounds <= covered:
        return 0
    return data.balance.army.starving_units_lost_per_round


def grow(state: CivState, data: CivData, ctx: TurnContext) -> None:
    """The growth step: a city that has collected enough surplus food gains one population."""
    needed = data.balance.city.growth_food
    for city in state.cities:
        if city.food >= needed:
            ctx.emit(
                "city_grew",
                {"city": city.id, "population": city.population + 1, "food": city.food - needed},
                visible_to=[city.owner],
            )


# --- events -----------------------------------------------------------------
# Events carry outcomes, not rules: applying one needs no game data, so a log
# rebuilds its state even after the numbers in the data files have changed.


def _city_founded(state: CivState, data: dict[str, Any]) -> None:
    state.cities.append(
        City(id=data["city"], owner=data["owner"], col=data["col"], row=data["row"])
    )


def _city_focus_set(state: CivState, data: dict[str, Any]) -> None:
    state.city(data["city"]).focus = data["focus"]


def _building_started(state: CivState, data: dict[str, Any]) -> None:
    city = state.city(data["city"])
    stock = state.nations[city.owner].stock
    for resource, amount in data["cost"].items():
        stock[resource] -= amount
    city.sites.append(Site(building=data["building"], rounds_left=data["rounds"]))


def _building_completed(state: CivState, data: dict[str, Any]) -> None:
    city = state.city(data["city"])
    # The first site of a kind is the oldest, so it is the one that is due.
    city.sites.remove(next(site for site in city.sites if site.building == data["building"]))
    city.buildings.append(data["building"])


def _construction_progressed(state: CivState, data: dict[str, Any]) -> None:
    for site in state.city(data["city"]).sites:
        site.rounds_left -= 1


def _building_demolished(state: CivState, data: dict[str, Any]) -> None:
    city = state.city(data["city"])
    city.buildings.remove(data["building"])
    _add(state.nations[city.owner].stock, data["refund"])


def _production(state: CivState, data: dict[str, Any]) -> None:
    nation = state.nations[data["player"]]
    nation.stock = dict(data["stock"])
    nation.hungry_rounds = data["hungry_rounds"]
    for city_id, food in data["stored"].items():
        state.city(city_id).food += food


def _city_grew(state: CivState, data: dict[str, Any]) -> None:
    city = state.city(data["city"])
    city.population = data["population"]
    city.food = data["food"]


APPLIERS: dict[str, Callable[[CivState, dict[str, Any]], None]] = {
    "city_founded": _city_founded,
    "city_focus_set": _city_focus_set,
    "building_started": _building_started,
    "building_completed": _building_completed,
    "construction_progressed": _construction_progressed,
    "building_demolished": _building_demolished,
    "production": _production,
    "city_grew": _city_grew,
}


# --- amounts of resources ---------------------------------------------------


def _amounts(amounts: Mapping[Resource, int]) -> Stock:
    return {resource: amounts.get(resource, 0) for resource in RESOURCES}


def _add(total: Stock, amounts: Mapping[Resource, int]) -> None:
    for resource, amount in amounts.items():
        total[resource] += amount


def _text(amounts: Mapping[Resource, int]) -> str:
    return ", ".join(f"{amounts[r]} {r}" for r in RESOURCES if r in amounts)
