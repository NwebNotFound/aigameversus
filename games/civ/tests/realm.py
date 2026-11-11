"""Shared by the tests of the game's systems: small maps and a state that is driven by events."""

import json
import random

from arena.engine.plugin import TurnContext
from arena.engine.rng import derive_rng
from arena.engine.types import Event
from games.civ import armies, economy
from games.civ.data_loader import CivData, load_civ_data
from games.civ.state import new_game
from games.civ.turn import apply_event, begin_round
from games.civ.world import Hex, WorldMap

DATA = load_civ_data()
PLAYERS = ["ada", "bo", "cy", "di", "ed", "flo"]
CENTER = (3, 2)
RING = [(2, 1), (3, 1), (2, 2), (4, 2), (2, 3), (3, 3)]  # the six tiles around CENTER
RICH = {"food": 99, "wood": 99, "iron": 99, "gold": 99}


def flat_map(kind: str, tiles: dict[Hex, str] | None = None) -> WorldMap:
    """Seven by five tiles of one terrain, with the given tiles changed."""
    rows = [[kind] * 7 for _ in range(5)]
    for (col, row), other in (tiles or {}).items():
        rows[row][col] = other
    return WorldMap(rows=rows, starts=[])


def bare_map(tiles: dict[Hex, str] | None = None) -> WorldMap:
    """Mountains, which yield nothing, around a plain for a city at CENTER."""
    return flat_map("mountains", {CENTER: "plains", **(tiles or {})})


def with_building_rules(**changes) -> CivData:
    return DATA.model_copy(
        update={"building_rules": DATA.building_rules.model_copy(update=changes)}
    )


def reordered(value):
    """The same JSON data with the keys of every object in the opposite order."""
    if isinstance(value, dict):
        return {key: reordered(item) for key, item in reversed(value.items())}
    if isinstance(value, list):
        return [reordered(item) for item in value]
    return value


def with_balance(section: str, **changes) -> CivData:
    """The shipped data with other numbers in one section of balance.yaml."""
    changed = getattr(DATA.balance, section).model_copy(update=changes)
    return DATA.model_copy(update={"balance": DATA.balance.model_copy(update={section: changed})})


class Realm:
    """A state and the log of what happened to it, driven the way the turn flow drives it.

    It is as strict as the engine: a random stream can be asked for once, and
    event data must be plain JSON.
    """

    def __init__(self, world: WorldMap, players=("ada", "bo"), data: CivData = DATA, seed: int = 0):
        self.data = data
        self.state = new_game(players, data)
        self.state.world = world
        self.events: list[Event] = []
        self.seed = seed
        self.streams: set[tuple] = set()
        self.ctx = TurnContext(self._stream, self._record)

    def _stream(self, *key: str | int) -> random.Random:
        assert key not in self.streams, f"random stream {key} asked for twice"
        self.streams.add(key)
        return derive_rng(self.seed, *key)

    def _record(self, event: Event) -> None:
        assert json.loads(json.dumps(event.data)) == event.data, f"{event.type}: not plain JSON"
        self.events.append(event)
        apply_event(self.state, event)

    def found(self, owner: str, tile: Hex, *buildings: str, population: int = 1) -> str:
        """A city of that nation, for a test that needs it grown or built up already."""
        city_id = economy.found_city(self.state, self.ctx, owner, tile)
        self.state.city(city_id).population = population
        self.state.city(city_id).buildings.extend(buildings)
        return city_id

    def army(self, owner: str, tile: Hex, *kinds: str, bonus: int = 0) -> str:
        """An army of these units on the tile, for a test that needs one standing there."""
        army_id = f"a{self.state.armies_raised + 1}"
        col, row = tile
        units = [{"kind": kind, "bonus": bonus} for kind in kinds]
        self.ctx.emit(
            "army_raised",
            {"army": army_id, "owner": owner, "col": col, "row": row, "units": units, "cost": {}},
            visible_to=[owner],
        )
        return army_id

    def keep(self, units: dict[str, list[str]]) -> None:
        """Make these the only units there are: one army per nation that has any."""
        self.state.armies = []
        for player, kinds in units.items():
            if kinds:
                self.army(player, (0, 0), *kinds)

    def build(self, player: str, city_id: str, building: str) -> None:
        economy.build(self.state, self.data, self.ctx, player, city_id, building)

    def start_round(self) -> None:
        begin_round(self.state, self.ctx)
        economy.finish_construction(self.state, self.ctx)

    def end_round(self) -> None:
        economy.produce(self.state, self.data, self.ctx)
        armies.starve(self.state, self.data, self.ctx)
        economy.grow(self.state, self.data, self.ctx)

    def round(self, units: dict[str, list[str]] | None = None) -> None:
        """A round without orders. With `units`, the nations keep exactly those in it."""
        self.start_round()
        if units is not None:
            self.keep(units)
        self.end_round()

    def stock(self, player: str = "ada") -> dict[str, int]:
        return self.state.nations[player].stock

    def yields(self, city_id: str) -> dict[str, int]:
        return economy.city_yields(self.state, self.data, city_id)

    def worked(self, city_id: str) -> list[Hex]:
        return economy.worked_tiles(self.state, self.data, city_id)

    def units(self, army_id: str) -> list[str]:
        return [troop.kind for troop in self.state.army(army_id).units]

    def of_type(self, type: str) -> list[dict]:
        return [event.data for event in self.events if event.type == type]
