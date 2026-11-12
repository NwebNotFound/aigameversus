"""What one nation sees at the start of its round, small enough for one call per nation.

    observation = observe(state, data, "ada", scoreboard=scoreboard, extras={...})

The field names are those of docs/civ-interfaces.md ("Observation of a nation"). Only the
nation's own things in full; of the others only what the fog lets through: the terrain of the
tiles it sees, and the cities and armies standing on them (an army shows its size, not its
makeup). What other systems own (treaties, offers, messages, refused orders, the gold-hold
counter) is passed in ``extras`` until the state holds it:

    reputation, production_modifier, gold_held_rounds, relations, offers, messages, refused,
    last_round

``plan`` is the nation's own text from last round, shown back to it and to nobody else.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from games.civ import armies, economy, fog, victory
from games.civ.data_loader import CivData
from games.civ.state import Army, City, CivState
from games.civ.world import Hex, distance

FOG = "?"
REACH_LIMIT = 40  # most tiles listed per army; the rest are cut, nearest first
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


def observe(
    state: CivState,
    data: CivData,
    player: str,
    *,
    scoreboard: dict[str, Any],
    extras: dict[str, Any] | None = None,
    plan: str | None = None,
) -> dict[str, Any]:
    """`scoreboard` is the public one (D-128, `plugin.scoreboard`): the city totals and counts the
    victory lines use come from it, never from counting cities in the state."""
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
        "rounds_total": victory.round_limit(state, data),
        "victory": _victory(state, data, player, extras, scoreboard),
        "stock": dict(nation.stock),
        "income_per_round": dict(income),
        "unpaid_rounds": nation.hungry_rounds,
        "reputation": extras.get("reputation", 50),
        "production_modifier": extras.get("production_modifier", 1.0),
        "your_plan_from_last_round": plan,
        "refused": extras.get("refused", []),
        "last_round": extras.get("last_round", []),
        "messages": extras.get("messages", []),
        "offers": extras.get("offers", []),
        "relations": extras.get("relations", {}),
        "cities": [_city(state, data, c) for c in mine_cities],
        "armies": [_army(state, data, a) for a in mine_armies],
        "legal": _legal(state, data, player, mine_cities),
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


def _legal(
    state: CivState, data: CivData, player: str, cities: list[City]
) -> dict[str, dict[str, Any]]:
    """What each city may order now (a model need not guess): buildings with their cost, units
    with the most one order can pay for, and the cost of one of each unit listed."""
    per_city: dict[str, Any] = {}
    unit_cost: dict[str, dict[str, int]] = {}
    for city in cities:
        build = {
            b: dict(data.buildings[b].cost)
            for b in sorted(data.buildings)
            if economy.build_problem(state, data, player, city.id, b) is None
        }
        train = _trainable(state, data, player, city)
        unit_cost.update({unit: dict(data.units[unit].cost) for unit in train})
        per_city[city.id] = {"build": build, "train": train}
    return {"cities": per_city, "unit_cost": unit_cost}


def _trainable(state: CivState, data: CivData, player: str, city: City) -> dict[str, int]:
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


def _victory(
    state: CivState, data: CivData, player: str, extras: dict[str, Any], scoreboard: dict[str, Any]
) -> dict[str, Any]:
    """How far the nation is from each way to win, and the closest one."""
    rules = data.victory
    mine = [c for c in state.cities if c.owner == player]  # its own cities, for its own score
    total, need = scoreboard["cities_total"], scoreboard["domination_needed"]
    held_cities = scoreboard["cities"][player]
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
    last = victory.round_limit(state, data)
    left = last - state.round
    gaps = {
        "domination": max(0, need - held_cities) * 3,
        "economy": max(0, rules.economy.hold_rounds - held)
        + (max(0, rules.economy.gold - gold) // 40),
    }
    return {
        "domination": f"{held_cities} of {need} cities needed ({total} exist)",
        "economy": f"{gold} of {rules.economy.gold} gold, held {held} of "
        f"{rules.economy.hold_rounds} rounds",
        "score": f"{score} now; the highest score wins after round {last} ({left} rounds left)",
        "closest_win": min(gaps, key=lambda kind: gaps[kind]),
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
    }


def _army(state: CivState, data: CivData, army: Army) -> dict[str, Any]:
    moved = army.moved_in_round == state.round
    ways = [] if moved else sorted(armies.reachable(state, data, army.id))
    near = sorted(ways, key=lambda t: (distance(army.tile, t), t))[:REACH_LIMIT]
    return {
        "id": army.id,
        "tile": [army.col, army.row],
        "units": dict(Counter(troop.kind for troop in army.units)),
        "move_points": armies.movement(data, army),
        "moved": moved,
        "reachable": [list(t) for t in near],
        "can_settle": armies.settle_problem(state, data, army.owner, army.id) is None,
    }
