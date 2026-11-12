"""Combat in Throne of Tokens: attacks, battles, conquest, pillage, fortifying, war weariness.

An attack is ordered during the army orders and fought afterwards, all
attacks of a round in the order they were given (docs/civ-interfaces.md):

    if (problem := attack_problem(state, data, "ada", "a1", (5, 4))) is None:
        attack(state, data, ctx, "ada", "a1", (5, 4))  # walks next to the target
    fortify(state, ctx, "ada", "a2")  # also: pillage
    resolve(state, data, ctx)  # the combat step: every ordered attack is fought
    weariness(state, data, ctx)  # late in the round: rounds at war cost production

Only nations at war fight, or anyone and a neutral army or city. Every
number comes from ``data/units.yaml``, ``data/terrain.yaml``,
``data/buildings.yaml`` and ``data/balance.yaml`` (``army``, ``combat``,
``conquest``, ``war_weariness``). Randomness: ``ctx.rng("combat", round,
battle)``.
"""

from __future__ import annotations

import math
import random
from collections.abc import Callable, Sequence
from typing import Any

from arena.engine.plugin import TurnContext
from games.civ import diplomacy
from games.civ.armies import _not_their_army, army_viewpoints, reachable
from games.civ.data_loader import CivData
from games.civ.economy import city_viewpoints, must_be_legal, weary_modifier
from games.civ.fog import visible_tiles
from games.civ.state import NEUTRAL, Army, City, CivState, Troop
from games.civ.world import Hex

# --- who may fight whom ------------------------------------------------------


def hostile(state: CivState, a: str, b: str) -> bool:
    """Whether a and b fight: at war, or either is neutral."""
    return a != b and (NEUTRAL in (a, b) or diplomacy.at_war(state, a, b))


def capital(state: CivState, nation: str) -> City | None:
    """The city on the nation's start tile, whoever holds it now."""
    start = next((s for s in state.world.starts if s.player == nation), None)
    if start is None:
        return None
    return next((c for c in state.cities if c.tile == (start.col, start.row)), None)


def _defenders(
    state: CivState, tile: Hex, attacker: str
) -> tuple[str | None, list[Army], City | None]:
    """Who holds the tile against the attacker: (owner, armies, city), owner None if nobody."""
    tile = tuple(tile)
    armies = [a for a in state.armies if a.tile == tile and a.owner != attacker]
    city = next((c for c in state.cities if c.tile == tile and c.owner != attacker), None)
    owner = armies[0].owner if armies else (city.owner if city else None)
    return (
        owner,
        [a for a in armies if a.owner == owner],
        city if city and city.owner == owner else None,
    )


def holder(state: CivState, tile: Hex, nation: str) -> str | None:
    """Who other than `nation` holds the tile with an army or a city, or None."""
    return _defenders(state, tile, nation)[0]


def sight(state: CivState, data: CivData, nation: str) -> set[Hex]:
    """The tiles the nation sees this round, around its cities and armies."""
    viewpoints = city_viewpoints(state, data, nation) + army_viewpoints(state, data, nation)
    return visible_tiles(state.world, viewpoints)


# --- orders --------------------------------------------------------------------


def attack_problem(
    state: CivState, data: CivData, player: str, army_id: str, target: Hex
) -> str | None:
    if problem := _not_their_army(state, player, army_id):
        return problem
    army = state.army(army_id)
    if army.moved_in_round == state.round:
        return f"{army_id} already moved this round. An army moves or attacks once per round."
    if not strength(data, army.units):
        return f"{army_id} has no fighting units."
    col, row = target
    if player != NEUTRAL and tuple(target) not in sight(state, data, player):
        # The same answer whatever stands there: a refusal must not show what the fog hides.
        return f"You do not see ({col}, {row}). An attack needs a target in sight: move closer."
    owner, armies, city = _defenders(state, target, player)
    if owner is None:
        return f"Nothing of another nation stands on ({col}, {row}). Move there."
    if not hostile(state, player, owner):
        return f"You are not at war with {owner}. Declare war first to attack ({col}, {row})."
    if tuple(target) not in reachable(state, data, army_id):
        return f"{army_id} cannot reach ({col}, {row}) this round."
    return None


def attack(
    state: CivState, data: CivData, ctx: TurnContext, player: str, army_id: str, target: Hex
) -> None:
    """Walk the army next to the target; the battle is fought in `resolve`."""
    must_be_legal(attack_problem(state, data, player, army_id, target))
    path = reachable(state, data, army_id)[tuple(target)][:-1]
    if path:
        ctx.emit(
            "army_moved",
            {"army": army_id, "path": [[c, r] for c, r in path]},
            visible_to=[player],
        )
    col, row = target
    ctx.emit("attack_ordered", {"army": army_id, "target": [col, row]}, visible_to=[player])


def fortify_problem(state: CivState, player: str, army_id: str) -> str | None:
    if problem := _not_their_army(state, player, army_id):
        return problem
    if state.army(army_id).moved_in_round == state.round:
        return f"{army_id} moved this round; it can fortify in a round it stays."
    return None


def fortify(state: CivState, ctx: TurnContext, player: str, army_id: str) -> None:
    """The army digs in: stronger in defence from the next round, until it moves."""
    must_be_legal(fortify_problem(state, player, army_id))
    ctx.emit(
        "army_fortified", {"army": army_id, "from_round": state.round + 1}, visible_to=[player]
    )


def pillage_problem(state: CivState, player: str, army_id: str) -> str | None:
    if problem := _not_their_army(state, player, army_id):
        return problem
    army = state.army(army_id)
    if army.moved_in_round == state.round:
        return f"{army_id} already moved this round."
    city = _pillage_target(state, army)
    if city is None:
        return (
            f"{army_id} stands next to no city of a nation it is at war with that has a building."
        )
    return None


def pillage(state: CivState, data: CivData, ctx: TurnContext, player: str, army_id: str) -> None:
    """Burn the newest building of a hostile city next to the army and carry off loot."""
    must_be_legal(pillage_problem(state, player, army_id))
    city = _pillage_target(state, state.army(army_id))
    building = city.buildings[-1]
    share = data.balance.conquest.pillage_loot_share
    loot = {r: math.floor(n * share) for r, n in data.buildings[building].cost.items()}
    ctx.emit(
        "city_pillaged",
        {
            "city": city.id,
            "army": army_id,
            "by": player,
            "building": building,
            "loot": {r: n for r, n in loot.items() if n},
        },
        visible_to=sorted({player, city.owner} - {NEUTRAL}),
    )


def _pillage_target(state: CivState, army: Army) -> City | None:
    near = set(state.world.within(army.tile, 1))
    return next(
        (
            c
            for c in state.cities
            if c.tile in near and c.buildings and hostile(state, army.owner, c.owner)
        ),
        None,
    )


# --- the combat step -------------------------------------------------------------


def resolve(state: CivState, data: CivData, ctx: TurnContext) -> None:
    """Fight every attack of the round, in the order they were ordered."""
    for index, order in enumerate(list(state.attacks)):
        army_id, target = order["army"], tuple(order["target"])
        army = next((a for a in state.armies if a.id == army_id), None)
        owner, defenders, city = _defenders(state, target, army.owner) if army else (None, [], None)
        if army is None or owner is None or not hostile(state, army.owner, owner):
            reason = "gone" if army is None else "nothing left to attack"
            visible = [army.owner] if army else []
            ctx.emit("attack_called_off", {"army": army_id, "reason": reason}, visible_to=visible)
            continue
        if defenders:
            won = _battle(state, data, ctx, index, army, target, owner, defenders, city)
            if not won:
                continue
        _enter(state, data, ctx, army, target, city)


def _battle(
    state: CivState,
    data: CivData,
    ctx: TurnContext,
    index: int,
    army: Army,
    target: Hex,
    owner: str,
    defenders: list[Army],
    city: City | None,
) -> bool:
    """One battle for the target tile. True if the attacker won it."""
    rng = ctx.rng("combat", state.round, index)
    attackers = list(army.units)
    held = [(a.id, i, t) for a in defenders for i, t in enumerate(a.units)]
    walls = bool(city and "wall" in city.buildings)
    terrain = data.terrain[state.world.terrain(target)]
    fortified = all(
        a.fortified_from is not None and a.fortified_from <= state.round for a in defenders
    )
    defence = terrain.defense + (data.balance.army.fortify_defense if fortified else 0)
    if city is not None:
        defence += sum(data.buildings[b].effects.city_defense for b in city.buildings)
    attack_bonus = terrain.attacker_modifier
    lost_a: set[int] = set()
    lost_d: set[int] = set()
    low, high = data.balance.combat.random_factor.min, data.balance.combat.random_factor.max
    luck_a, luck_d = rng.uniform(low, high), rng.uniform(low, high)

    def powers(ranged_only: bool) -> tuple[float, float]:
        mine = [t for i, t in enumerate(attackers) if i not in lost_a]
        theirs = [t for j, (_, _, t) in enumerate(held) if j not in lost_d]
        a = _power(data, mine, theirs, 1 + attack_bonus, walls, False, ranged_only) * luck_a
        d = _power(data, theirs, mine, 1 + defence, False, city is not None, ranged_only) * luck_d
        return a, d

    for _ in range(data.balance.combat.ranged_rounds):  # archers fire first
        shot_a, shot_d = powers(ranged_only=True)
        total_a, total_d = powers(ranged_only=False)
        ranged = data.balance.combat.ranged_loss_factor
        _take(rng, lost_d, len(held), _share(shot_a, total_d) * ranged)
        _take(rng, lost_a, len(attackers), _share(shot_d, total_a) * ranged)
    power_a, power_d = powers(ranged_only=False)
    attacker_won = power_a > power_d  # a tie holds the tile
    winner_power, loser_power = max(power_a, power_d), min(power_a, power_d)
    # In proportion to the power ratio: 2:1 costs the loser all at a factor of 0.5, 1.2:1 60 %.
    ratio = winner_power / loser_power if loser_power else math.inf
    loser_share = min(1.0, ratio * data.balance.combat.loser_loss_factor)
    winner_share = (loser_power / winner_power if winner_power else 0) * (
        data.balance.combat.winner_loss_factor
    )
    if attacker_won:
        _take(rng, lost_d, len(held), loser_share, at_least_one=True)
        _take(rng, lost_a, len(attackers), winner_share)
    else:
        _take(rng, lost_a, len(attackers), loser_share, at_least_one=True)
        _take(rng, lost_d, len(held), winner_share)
    col, row = target
    side_d = {
        "nation": owner,
        "armies": [a.id for a in defenders],
        "city": city.id if city else None,
        "power": round(power_d, 2),
        "lost": sorted(held[j][2].kind for j in lost_d),
    }
    ctx.emit(
        "battle",
        {
            "tile": [col, row],
            "round": state.round,
            "attacker": {
                "nation": army.owner,
                "army": army.id,
                "power": round(power_a, 2),
                "lost": sorted(attackers[i].kind for i in lost_a),
            },
            "defender": side_d,
            "winner": army.owner if attacker_won else owner,
        },
        visible_to=sorted({army.owner, owner} - {NEUTRAL}),
    )
    if lost_a:
        _lose(ctx, army, sorted(lost_a))
    for defender in defenders:
        mine = sorted(i for j, (aid, i, _) in enumerate(held) if aid == defender.id and j in lost_d)
        if mine:
            _lose(ctx, defender, mine)
    still = [a for a in state.armies if a.tile == tuple(target) and a.owner == owner]
    return attacker_won and not still and any(a.id == army.id for a in state.armies)


def _enter(
    state: CivState, data: CivData, ctx: TurnContext, army: Army, target: Hex, city: City | None
) -> None:
    """The attacker takes the empty tile; a city on it changes hands."""
    col, row = target
    ctx.emit("army_moved", {"army": army.id, "path": [[col, row]]}, visible_to=[army.owner])
    if city is None:
        return
    conquest = data.balance.conquest
    was_capital = capital(state, city.owner) is city and city.owner in state.nations
    ctx.emit(
        "city_conquered",
        {
            "city": city.id,
            "army": army.id,
            "from": city.owner,
            "to": army.owner,
            "round": state.round,
            "population": max(city.population - conquest.population_loss, 1),
            # the old owner's production suffers until this round, if it was its capital
            "capital_lost_until": state.round + conquest.capital_lost_rounds
            if was_capital
            else None,
        },
        visible_to=None,  # the map changes hands: everyone hears of it
    )


def _power(
    data: CivData,
    units: Sequence[Troop],
    enemies: Sequence[Troop],
    bonus: float,
    walls: bool,
    in_city: bool,
    ranged_only: bool,
) -> float:
    """Σ strength × counter × (1 + bonuses) of these units against those."""
    kinds = [t.kind for t in enemies]
    total = 0.0
    for troop in units:
        unit = data.units[troop.kind]
        if ranged_only and not unit.ranged:
            continue
        strength = unit.strength + troop.bonus
        for counter in unit.counters:  # stronger by the share of enemies it counters
            if kinds:
                strength *= 1 + (counter.multiplier - 1) * kinds.count(counter.target) / len(kinds)
        if walls:
            strength *= unit.vs_walls_multiplier
        extra = unit.city_defense if in_city else 0
        total += strength * (bonus + extra)
    return total


def strength(data: CivData, units: Sequence[Troop]) -> int:
    return sum(data.units[t.kind].strength + t.bonus for t in units)


def _share(power: float, against: float) -> float:
    if not against:
        return 1.0 if power else 0.0
    return min(power / against, 1.0) if power else 0.0


def _take(
    rng: random.Random, lost: set[int], size: int, share: float, *, at_least_one: bool = False
) -> None:
    """Mark round(share x the survivors) more of `size` units as lost, picked at random."""
    alive = [i for i in range(size) if i not in lost]
    count = min(len(alive), round(share * len(alive)))
    if at_least_one and alive:
        count = max(count, 1)
    lost.update(rng.sample(alive, count))


def _lose(ctx: TurnContext, army: Army, indexes: list[int]) -> None:
    ctx.emit(
        "units_lost",
        {"army": army.id, "indexes": indexes, "reason": "battle"},
        visible_to=[] if army.owner == NEUTRAL else [army.owner],
    )


# --- war weariness -----------------------------------------------------------------


def weariness(state: CivState, data: CivData, ctx: TurnContext) -> None:
    """Late in the round: a nation at war is one round wearier; at peace it recovers at once."""
    for nation, kept in state.nations.items():
        rounds = kept.weary_rounds + 1 if diplomacy.wars_of(state, nation) else 0
        if rounds != kept.weary_rounds:
            ctx.emit(
                "war_weariness",
                {"nation": nation, "rounds": rounds, "modifier": weary_modifier(data, rounds)},
                visible_to=[nation],
            )


# --- events --------------------------------------------------------------------------


def _attack_ordered(state: CivState, data: dict[str, Any]) -> None:
    army = state.army(data["army"])
    army.moved_in_round = state.round
    army.fortified_from = None
    state.attacks.append({"army": data["army"], "target": data["target"]})


def _attack_done(state: CivState, data: dict[str, Any]) -> None:
    army_id = data["army"] if "army" in data else data["attacker"]["army"]
    state.attacks = [a for a in state.attacks if a["army"] != army_id]


def _battle_fought(state: CivState, data: dict[str, Any]) -> None:
    _attack_done(state, data)
    nations = [data["attacker"]["nation"], data["defender"]["nation"]]
    state.battles.append(
        {"round": data["round"], "tile": data["tile"], "winner": data["winner"], "nations": nations}
    )


def _army_fortified(state: CivState, data: dict[str, Any]) -> None:
    state.army(data["army"]).fortified_from = data["from_round"]


def _city_conquered(state: CivState, data: dict[str, Any]) -> None:
    city = state.city(data["city"])
    loser = data["from"]
    city.owner = data["to"]
    city.population = data["population"]
    city.conquered_round = data["round"]
    city.sites = []  # what the old owner was building is lost
    if data["capital_lost_until"] is not None:
        state.nations[loser].capital_lost_until = data["capital_lost_until"]
    state.attacks = [a for a in state.attacks if a["army"] != data["army"]]


def _city_pillaged(state: CivState, data: dict[str, Any]) -> None:
    city = state.city(data["city"])
    city.buildings.remove(data["building"])
    army = state.army(data["army"])
    army.moved_in_round = state.round
    army.fortified_from = None
    if data["by"] in state.nations:
        stock = state.nations[data["by"]].stock
        for resource, amount in data["loot"].items():
            stock[resource] += amount


def _war_weariness(state: CivState, data: dict[str, Any]) -> None:
    state.nations[data["nation"]].weary_rounds = data["rounds"]


APPLIERS: dict[str, Callable[[CivState, dict[str, Any]], None]] = {
    "attack_ordered": _attack_ordered,
    "attack_called_off": _attack_done,
    "battle": _battle_fought,
    "army_fortified": _army_fortified,
    "city_conquered": _city_conquered,
    "city_pillaged": _city_pillaged,
    "war_weariness": _war_weariness,
}
