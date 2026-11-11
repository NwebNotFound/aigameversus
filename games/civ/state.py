"""The state of a Throne of Tokens match, as far as the game is built.

It holds what is true now and no rules. It changes only when an event is
applied (``apply_event`` in ``turn.py``), so the event log of a match rebuilds
it exactly.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import get_args

from pydantic import BaseModel

from games.civ.data_loader import CivData, Focus, Resource
from games.civ.world import Hex, WorldMap

Stock = dict[Resource, int]


class Nation(BaseModel):
    stock: Stock  # what the nation owns of every resource; never below 0
    hungry_rounds: int = 0  # rounds in a row in which upkeep was not paid in full


class Site(BaseModel):
    """A building under construction. It takes a building slot and does nothing yet."""

    building: str
    rounds_left: int


class City(BaseModel):
    id: str  # "c1", "c2", ... in the order the cities were founded
    owner: str
    col: int
    row: int
    population: int = 1
    food: int = 0  # surplus food collected towards the next population
    focus: Focus = "growth"
    buildings: list[str] = []
    sites: list[Site] = []

    @property
    def tile(self) -> Hex:
        return self.col, self.row


class Troop(BaseModel):
    """One unit of an army."""

    kind: str  # a unit id from the data
    bonus: int = 0  # strength added where it was trained


class Army(BaseModel):
    id: str  # "a1", "a2", ... in the order the armies were raised; never used twice
    owner: str
    col: int
    row: int
    units: list[Troop]  # never empty: an army that loses its last unit is gone

    @property
    def tile(self) -> Hex:
        return self.col, self.row


class CivState(BaseModel):
    round: int = 0  # the round being played; 0 before the first
    world: WorldMap = WorldMap(rows=[], starts=[])
    nations: dict[str, Nation]
    cities: list[City] = []  # in founding order: the older city wins a tie over a tile
    armies: list[Army] = []
    armies_raised: int = 0  # how many armies there have ever been, for the next id

    def city(self, city_id: str) -> City:
        return next(city for city in self.cities if city.id == city_id)

    def army(self, army_id: str) -> Army:
        return next(army for army in self.armies if army.id == army_id)

    def units_of(self, player: str) -> list[str]:
        """The kinds of all units the nation keeps, army by army."""
        return [troop.kind for army in self.armies if army.owner == player for troop in army.units]


def new_game(players: Sequence[str], data: CivData) -> CivState:
    """The state before the map is drawn: every nation with its starting stock."""
    start = data.balance.start.resources
    stock = {resource: start.get(resource, 0) for resource in get_args(Resource)}
    return CivState(nations={player: Nation(stock=dict(stock)) for player in players})
