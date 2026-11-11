"""The armies of Throne of Tokens: training units, organising armies and moving them.

An army is a stack of units on one tile. Like the economy, every function
that changes something emits an event private to the army's nation, and the
functions in ``APPLIERS`` are the only code here that touches the state.

    deploy_start_units(state, data, ctx)  # once, after the capitals are founded
    if (problem := train_problem(state, data, "ada", "c1", "spearman", 2)) is None:
        train(state, data, ctx, "ada", "c1", "spearman", 2)  # a new army in the city
    move(state, data, ctx, "ada", "a1", (4, 2))  # also: split, merge, disband, settle
    starve(state, data, ctx)  # after production: unpaid upkeep costs units

All numbers come from ``data/units.yaml``, ``data/terrain.yaml`` and
``data/balance.yaml`` (``army``, ``start``, ``city.min_distance``).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from decimal import ROUND_CEILING, Decimal
from typing import Any

from arena.engine.plugin import TurnContext
from games.civ.data_loader import CivData, Resource
from games.civ.economy import (
    cannot_pay,
    found_city,
    must_be_legal,
    not_their_city,
    units_lost_to_hunger,
)
from games.civ.state import Army, CivState, Troop
from games.civ.world import Hex, distance

# --- what an army can do ----------------------------------------------------


def movement(data: CivData, army: Army) -> int:
    """The movement points of the army in a round: those of its slowest unit."""
    return min(data.units[troop.kind].movement for troop in army.units)


def reachable(state: CivState, data: CivData, army_id: str) -> dict[Hex, list[Hex]]:
    """Every tile the army can end this round on, with the tiles it walks over to get there.

    Entering a tile costs its movement cost, and leaving a river costs the
    crossing on top. An army with points left may always take one more step:
    a tile that costs more than it has left ends its move there. So every
    army gets one tile far, and only fast ones feel the terrain.
    """
    army, world = state.army(army_id), state.world
    best: dict[Hex, tuple[int, list[Hex]]] = {army.tile: (movement(data, army), [])}
    edge = [army.tile]
    while edge:
        here = edge.pop(0)
        left, path = best[here]
        if left <= 0:
            continue
        crossing = data.terrain[world.terrain(here)].crossing_extra_cost
        for tile in world.within(here, 1):
            cost = data.terrain[world.terrain(tile)].movement_cost
            if tile == here or cost is None:
                continue
            after = left - cost - crossing
            # More points left is better; with the same points, the shorter way.
            if tile not in best or (after, -len(path) - 1) > (best[tile][0], -len(best[tile][1])):
                best[tile] = (after, [*path, tile])
                edge.append(tile)
    del best[army.tile]
    return {tile: path for tile, (_, path) in best.items()}


def army_viewpoints(state: CivState, data: CivData, player: str) -> list[tuple[Hex, int]]:
    """Where the nation's armies stand and how far each sees, for ``fog.visible_tiles``."""
    sight = data.balance.map.fog_vision_radius
    return [
        (army.tile, sight + max(data.units[troop.kind].vision_bonus for troop in army.units))
        for army in state.armies
        if army.owner == player
    ]


def training_cost(
    state: CivState, data: CivData, city_id: str, unit_id: str, count: int
) -> dict[Resource, int]:
    """What the city pays for these units: the whole order, rounded up after its discounts."""
    modifiers = (
        data.buildings[building].effects.training_cost_modifier
        for building in state.city(city_id).buildings
    )
    discount = sum((Decimal(str(modifier)) for modifier in modifiers), Decimal(0))
    factor = max(1 + discount, Decimal(0))
    return {
        resource: int((amount * count * factor).to_integral_value(ROUND_CEILING))
        for resource, amount in data.units[unit_id].cost.items()
    }


# --- orders -----------------------------------------------------------------
# As in the economy: a `*_problem` function returns None or a message for the
# player, and the order itself must be legal.


def deploy_start_units(state: CivState, data: CivData, ctx: TurnContext) -> None:
    """Give every nation its starting units, as one army on its capital."""
    kinds = [group.unit for group in data.balance.start.units for _ in range(group.count)]
    for start in state.world.starts:
        _raise(state, ctx, start.player, start.tile, [Troop(kind=kind) for kind in kinds], {})


def train_problem(
    state: CivState, data: CivData, player: str, city_id: str, unit_id: str, count: int
) -> str | None:
    if problem := not_their_city(state, player, city_id):
        return problem
    unit = data.units.get(unit_id)
    if unit is None:
        return f"There is no unit '{unit_id}'. Units: {', '.join(data.units)}."
    limit = data.balance.army.max_units
    if not 1 <= count <= limit:
        return f"One order trains 1 to {limit} units, not {count}."
    if unit.trained_in is not None and unit.trained_in not in state.city(city_id).buildings:
        return (
            f"A {unit_id} is trained in a {unit.trained_in}, and {city_id} has none. "
            f"Build one there or train in a city that has one."
        )
    cost = training_cost(state, data, city_id, unit_id, count)
    return cannot_pay(state.nations[player].stock, cost, f"{count} {unit_id} cost")


def train(
    state: CivState,
    data: CivData,
    ctx: TurnContext,
    player: str,
    city_id: str,
    unit_id: str,
    count: int,
) -> str:
    """Pay for the units and put them in the city as a new army. Returns the army's id."""
    must_be_legal(train_problem(state, data, player, city_id, unit_id, count))
    city = state.city(city_id)
    fights = data.units[unit_id].strength > 0
    bonus = sum(
        data.buildings[building].effects.trained_unit_strength_bonus for building in city.buildings
    )
    units = [Troop(kind=unit_id, bonus=bonus if fights else 0) for _ in range(count)]
    cost = training_cost(state, data, city_id, unit_id, count)
    return _raise(state, ctx, player, city.tile, units, cost)


def move_problem(
    state: CivState, data: CivData, player: str, army_id: str, target: Hex
) -> str | None:
    if problem := _not_their_army(state, player, army_id):
        return problem
    if state.army(army_id).moved_in_round == state.round:
        return f"{army_id} already moved this round. An army moves once per round."
    ways = reachable(state, data, army_id)
    if tuple(target) in ways:
        return None
    col, row = target
    near = ", ".join(f"({c}, {r})" for c, r in sorted(ways))
    return f"{army_id} cannot reach ({col}, {row}) this round. It can move to: {near or 'nowhere'}."


def move(
    state: CivState, data: CivData, ctx: TurnContext, player: str, army_id: str, target: Hex
) -> None:
    """Walk the army to a tile it can reach. That was its move for this round."""
    must_be_legal(move_problem(state, data, player, army_id, target))
    path = reachable(state, data, army_id)[tuple(target)]
    ctx.emit(
        "army_moved",
        {"army": army_id, "path": [[col, row] for col, row in path]},
        visible_to=[player],
    )


def split_problem(state: CivState, player: str, army_id: str, kinds: Sequence[str]) -> str | None:
    if problem := _not_their_army(state, player, army_id):
        return problem
    have = [troop.kind for troop in state.army(army_id).units]
    if not kinds:
        return "Name the units to split off, for example ['spearman', 'spearman']."
    for kind in sorted(set(kinds)):
        if kinds.count(kind) > have.count(kind):
            return (
                f"{army_id} has {have.count(kind)} {kind}, not {kinds.count(kind)}. "
                f"Its units: {', '.join(have)}."
            )
    if len(kinds) == len(have):
        return f"A split must leave a unit behind, and these are all of {army_id}."
    return None


def split(
    state: CivState, ctx: TurnContext, player: str, army_id: str, kinds: Sequence[str]
) -> str:
    """Take units of these kinds out of the army as a new army on the same tile; returns its id."""
    must_be_legal(split_problem(state, player, army_id, kinds))
    indexes: list[int] = []
    for kind in kinds:  # the first units of each kind, in the army's order
        indexes.append(
            next(
                index
                for index, troop in enumerate(state.army(army_id).units)
                if troop.kind == kind and index not in indexes
            )
        )
    new_id = _next_id(state)
    ctx.emit(
        "army_split",
        {"army": army_id, "indexes": sorted(indexes), "new_army": new_id},
        visible_to=[player],
    )
    return new_id


def merge_problem(
    state: CivState, data: CivData, player: str, army_ids: Sequence[str]
) -> str | None:
    if len(set(army_ids)) < 2 or len(set(army_ids)) != len(army_ids):
        return "Name at least two different armies to merge."
    for army_id in army_ids:
        if problem := _not_their_army(state, player, army_id):
            return problem
    armies = [state.army(army_id) for army_id in army_ids]
    if len({army.tile for army in armies}) > 1:
        places = ", ".join(f"{army.id} at ({army.col}, {army.row})" for army in armies)
        return f"Armies merge on one tile: {places}. Move them together first."
    size, limit = sum(len(army.units) for army in armies), data.balance.army.max_units
    if size > limit:
        return f"Together they have {size} units, and an army holds at most {limit}."
    return None


def merge(
    state: CivState, data: CivData, ctx: TurnContext, player: str, army_ids: Sequence[str]
) -> None:
    """Join armies on one tile into the first of them."""
    must_be_legal(merge_problem(state, data, player, army_ids))
    ctx.emit(
        "armies_merged", {"into": army_ids[0], "armies": list(army_ids[1:])}, visible_to=[player]
    )


def disband_problem(state: CivState, player: str, army_id: str) -> str | None:
    return _not_their_army(state, player, army_id)


def disband(state: CivState, ctx: TurnContext, player: str, army_id: str) -> None:
    """Send the whole army home for good. Its upkeep ends with this round's production."""
    must_be_legal(disband_problem(state, player, army_id))
    ctx.emit("army_disbanded", {"army": army_id}, visible_to=[player])


def settle_problem(state: CivState, data: CivData, player: str, army_id: str) -> str | None:
    if problem := _not_their_army(state, player, army_id):
        return problem
    army = state.army(army_id)
    if not any(data.units[troop.kind].founds_city for troop in army.units):
        founders = [unit.id for unit in data.units.values() if unit.founds_city]
        return f"{army_id} has no unit that founds a city ({', '.join(founders)})."
    apart = data.balance.city.min_distance
    if any(distance(city.tile, army.tile) < apart for city in state.cities):
        return (
            f"A new city must be at least {apart} steps from every other city, and "
            f"{army_id} at ({army.col}, {army.row}) is closer to one. Move it first."
        )
    return None


def settle(state: CivState, data: CivData, ctx: TurnContext, player: str, army_id: str) -> str:
    """Found a city where the army stands; one of its settlers becomes the city. Returns its id."""
    must_be_legal(settle_problem(state, data, player, army_id))
    army = state.army(army_id)
    tile = army.tile
    settler = next(i for i, troop in enumerate(army.units) if data.units[troop.kind].founds_city)
    ctx.emit(
        "units_lost",
        {"army": army_id, "indexes": [settler], "reason": "settled"},
        visible_to=[player],
    )
    return found_city(state, ctx, player, tile)


def _raise(
    state: CivState,
    ctx: TurnContext,
    owner: str,
    tile: Hex,
    units: Sequence[Troop],
    cost: dict[Resource, int],
) -> str:
    army_id = _next_id(state)
    col, row = tile
    ctx.emit(
        "army_raised",
        {
            "army": army_id,
            "owner": owner,
            "col": col,
            "row": row,
            "units": [troop.model_dump() for troop in units],
            "cost": cost,
        },
        visible_to=[owner],
    )
    return army_id


def _next_id(state: CivState) -> str:
    return f"a{state.armies_raised + 1}"


def _not_their_army(state: CivState, player: str, army_id: str) -> str | None:
    own = [army.id for army in state.armies if army.owner == player]
    if army_id in own:
        return None
    # The same answer for an army of another nation: its existence stays hidden.
    return f"You have no army '{army_id}'. Your armies: {', '.join(own) or 'none'}."


# --- the step of a round ----------------------------------------------------


def starve(state: CivState, data: CivData, ctx: TurnContext) -> None:
    """After production: a nation that is too hungry loses units, picked at random."""
    for player in state.nations:
        units = [
            (army.id, index)
            for army in state.armies
            if army.owner == player
            for index in range(len(army.units))
        ]
        lost = min(units_lost_to_hunger(state, data, player), len(units))
        if not lost:
            continue
        picked = ctx.rng("hunger", state.round, player).sample(units, lost)
        for army_id in sorted({army_id for army_id, _ in picked}):
            indexes = sorted(index for picked_army, index in picked if picked_army == army_id)
            ctx.emit(
                "units_lost",
                {"army": army_id, "indexes": indexes, "reason": "starved"},
                visible_to=[player],
            )


# --- events -----------------------------------------------------------------


def _army_raised(state: CivState, data: dict[str, Any]) -> None:
    stock = state.nations[data["owner"]].stock
    for resource, amount in data["cost"].items():
        stock[resource] -= amount
    state.armies_raised += 1
    state.armies.append(
        Army(
            id=data["army"],
            owner=data["owner"],
            col=data["col"],
            row=data["row"],
            units=[Troop(**unit) for unit in data["units"]],
        )
    )


def _army_moved(state: CivState, data: dict[str, Any]) -> None:
    army = state.army(data["army"])
    army.col, army.row = data["path"][-1]
    army.moved_in_round = state.round


def _army_split(state: CivState, data: dict[str, Any]) -> None:
    army, taken = state.army(data["army"]), set(data["indexes"])
    units = army.units
    army.units = [troop for index, troop in enumerate(units) if index not in taken]
    state.armies_raised += 1
    state.armies.append(
        Army(
            id=data["new_army"],
            owner=army.owner,
            col=army.col,
            row=army.row,
            units=[troop for index, troop in enumerate(units) if index in taken],
            moved_in_round=army.moved_in_round,  # units that walked stay walked
        )
    )


def _armies_merged(state: CivState, data: dict[str, Any]) -> None:
    into = state.army(data["into"])
    for army_id in data["armies"]:
        joining = state.army(army_id)
        into.units.extend(joining.units)
        # If any part has moved this round, the whole has.
        moved = [a.moved_in_round for a in (into, joining) if a.moved_in_round is not None]
        into.moved_in_round = max(moved, default=None)
        state.armies.remove(joining)


def _army_disbanded(state: CivState, data: dict[str, Any]) -> None:
    state.armies.remove(state.army(data["army"]))


def _units_lost(state: CivState, data: dict[str, Any]) -> None:
    army, gone = state.army(data["army"]), set(data["indexes"])
    army.units = [troop for index, troop in enumerate(army.units) if index not in gone]
    if not army.units:
        state.armies.remove(army)


APPLIERS: dict[str, Callable[[CivState, dict[str, Any]], None]] = {
    "army_raised": _army_raised,
    "army_moved": _army_moved,
    "army_split": _army_split,
    "armies_merged": _armies_merged,
    "army_disbanded": _army_disbanded,
    "units_lost": _units_lost,
}
