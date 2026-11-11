"""What one nation sees at the start of its round, small enough for one call per nation.

    observation = observe(state, data, "ada")

Only its own things in full; of the others only what the fog lets through: the terrain of the
tiles it sees, and the cities and armies standing on them (an army shows its size, not its
makeup). Messages and treaties belong to diplomacy and are added there.
"""

from __future__ import annotations

import math
from collections import Counter
from typing import Any

from games.civ import armies, economy, fog
from games.civ.data_loader import CivData
from games.civ.state import Army, City, CivState
from games.civ.world import Hex, distance

FOG = "?"
# one character per terrain id, so a map row is a short string
GLYPHS = {
    "plains": "p",
    "forest": "f",
    "hills": "h",
    "iron_deposit": "I",
    "gold_vein": "G",
    "river": "r",
    "mountains": "M",
    "water": "~",
}


def glyph(terrain: str) -> str:
    return GLYPHS.get(terrain, terrain[:1] or FOG)


def visible_to(state: CivState, data: CivData, player: str) -> set[Hex]:
    """Every tile the nation sees: around its cities and armies."""
    viewpoints = economy.city_viewpoints(state, data, player) + armies.army_viewpoints(
        state, data, player
    )
    return fog.visible_tiles(state.world, viewpoints)


REACH_LIMIT = 40  # most tiles listed per army; the rest are cut, nearest first


def observe(
    state: CivState,
    data: CivData,
    player: str,
    *,
    extras: dict[str, Any] | None = None,
    changes: list[str] | None = None,
    plan: str | None = None,
) -> dict[str, Any]:
    """The nation's view. ``extras`` is what other systems know of it (diplomacy, victory
    counters): ``gold_held_rounds``, ``reputation``, ``offers``. ``changes`` are lines about what
    happened since its last turn; ``plan`` is its own text from last round, shown back to it."""
    extras = extras or {}
    seen = visible_to(state, data, player)
    mine_cities = [c for c in state.cities if c.owner == player]
    mine_armies = [a for a in state.armies if a.owner == player]
    income: Counter[str] = Counter()
    for city in mine_cities:
        income.update(economy.city_yields(state, data, city.id))
    nation = state.nations[player]
    return {
        "you": player,
        "round": state.round,
        "overview": {
            "stock": dict(nation.stock),
            "income_per_round": dict(income),
            "cities": len(mine_cities),
            "population": sum(c.population for c in mine_cities),
            "armies": len(mine_armies),
            "units": sum(len(a.units) for a in mine_armies),
            "unpaid_rounds": nation.hungry_rounds,
        },
        "win": _win(state, data, player, extras),
        "changed": changes or [],
        "your_plan_from_last_round": plan,
        "offers": extras.get("offers", []),
        "cities": [_city(state, data, c) for c in mine_cities],
        "armies": [_army(state, data, a) for a in mine_armies],
        "map": {
            "legend": {glyph(kind): kind for kind in data.terrain} | {FOG: "fog (not seen)"},
            "rows": ["".join(_row(line)) for line in fog.map_view(state.world, seen)],
        },
        "seen": {
            "cities": [
                {"id": c.id, "owner": c.owner, "tile": [c.col, c.row], "population": c.population}
                for c in state.cities
                if c.owner != player and c.tile in seen
            ],
            "armies": [
                {"id": a.id, "owner": a.owner, "tile": [a.col, a.row], "units": len(a.units)}
                for a in state.armies
                if a.owner != player and a.tile in seen
            ],
        },
    }


def _row(line: list[str | None]) -> list[str]:
    return [FOG if kind is None else glyph(kind) for kind in line]


def _cost(cost: dict[str, int]) -> str:
    return ", ".join(f"{amount} {resource}" for resource, amount in cost.items())


def _doable_builds(state: CivState, data: CivData, player: str, city: City) -> dict[str, str]:
    """Buildings the city can order now (affordable, a free slot), with their cost."""
    return {
        b: _cost(data.buildings[b].cost)
        for b in sorted(data.buildings)
        if economy.build_problem(state, data, player, city.id, b) is None
    }


def _doable_units(state: CivState, data: CivData, player: str, city: City) -> dict[str, int]:
    """Units the city can train now, with the most it can pay for in one order."""
    most = data.balance.army.max_units
    found = {}
    for unit in sorted(data.units):
        count = max(
            (
                n
                for n in range(1, most + 1)
                if armies.train_problem(state, data, player, city.id, unit, n) is None
            ),
            default=0,
        )
        if count:
            found[unit] = count
    return found


def _win(state: CivState, data: CivData, player: str, extras: dict[str, Any]) -> dict[str, Any]:
    """How far the nation is from each way to win, and the closest one."""
    rules = data.victory
    mine = [c for c in state.cities if c.owner == player]
    total = len(state.cities)  # assumed public: the share is checked against all cities
    need = max(1, math.ceil(rules.domination.city_share * total - 1e-9))
    gold = state.nations[player].stock["gold"]
    held = extras.get("gold_held_rounds", 0)
    reputation = extras.get("reputation", 50)
    score_rules = rules.round_limit.score
    score = (
        len(mine) * score_rules.per_city
        + sum(c.population for c in mine) * score_rules.per_population
        + gold // score_rules.gold_divisor
        + reputation // score_rules.reputation_divisor
    )
    left = rules.round_limit.rounds - state.round
    gaps = {
        "domination": max(0, need - len(mine)) * 3,
        "economy": max(0, rules.economy.hold_rounds - held)
        + (max(0, rules.economy.gold - gold) // 40),
    }
    closest = min(gaps, key=lambda kind: gaps[kind])
    return {
        "domination": f"{len(mine)} of {need} cities needed ({total} exist)",
        "economy": f"{gold} of {rules.economy.gold} gold, held {held} of "
        f"{rules.economy.hold_rounds} rounds",
        "score": f"{score} now; the highest score wins after round "
        f"{rules.round_limit.rounds} ({left} rounds left)",
        "closest_win": closest,
    }


def _city(state: CivState, data: CivData, city: City) -> dict[str, Any]:
    taken = len(city.buildings) + len(city.sites)
    return {
        "id": city.id,
        "tile": [city.col, city.row],
        "population": city.population,
        "focus": city.focus,
        "buildings": list(city.buildings),
        "building_now": [f"{s.building} ({s.rounds_left} rounds left)" for s in city.sites],
        "slots_free": economy.building_slots(data, city.population) - taken,
        "yields": economy.city_yields(state, data, city.id),
        "can_build": _doable_builds(state, data, city.owner, city),
        "can_train": _doable_units(state, data, city.owner, city),
    }


def _army(state: CivState, data: CivData, army: Army) -> dict[str, Any]:
    ways = (
        [] if army.moved_in_round == state.round else sorted(armies.reachable(state, data, army.id))
    )
    near = sorted(ways, key=lambda t: (distance(army.tile, t), t))[:REACH_LIMIT]
    return {
        "id": army.id,
        "tile": [army.col, army.row],
        "units": dict(Counter(troop.kind for troop in army.units)),
        "move_points": armies.movement(data, army),
        "moved": army.moved_in_round == state.round,
        "can_reach": [list(t) for t in near],
        "can_settle": armies.settle_problem(state, data, army.owner, army.id) is None,
    }
