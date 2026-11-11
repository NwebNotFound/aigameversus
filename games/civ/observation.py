"""What one nation sees at the start of its round, small enough for one call per nation.

    observation = observe(state, data, "ada")

Only its own things in full; of the others only what the fog lets through: the terrain of the
tiles it sees, and the cities and armies standing on them (an army shows its size, not its
makeup). Messages and treaties belong to diplomacy and are added there.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from games.civ import armies, economy, fog
from games.civ.data_loader import CivData
from games.civ.state import Army, City, CivState
from games.civ.world import Hex

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


def observe(state: CivState, data: CivData, player: str) -> dict[str, Any]:
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
        "cities": [_city(state, data, c) for c in mine_cities],
        "armies": [_army(data, a, state.round) for a in mine_armies],
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


def _army(data: CivData, army: Army, current_round: int) -> dict[str, Any]:
    return {
        "id": army.id,
        "tile": [army.col, army.row],
        "units": dict(Counter(troop.kind for troop in army.units)),
        "move_points": armies.movement(data, army),
        "moved": army.moved_in_round == current_round,
    }
