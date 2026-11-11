"""The state of a Throne of Tokens match, as far as the game is built.

It holds what is true now and no rules. It changes only when an event is
applied (``apply_event`` in ``economy.py``), so the event log of a match
rebuilds it exactly.
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


class CivState(BaseModel):
    world: WorldMap = WorldMap(rows=[], starts=[])
    nations: dict[str, Nation]
    cities: list[City] = []  # in founding order: the older city wins a tie over a tile

    def city(self, city_id: str) -> City:
        return next(city for city in self.cities if city.id == city_id)


def new_game(players: Sequence[str], data: CivData) -> CivState:
    """The state before the map is drawn: every nation with its starting stock."""
    start = data.balance.start.resources
    stock = {resource: start.get(resource, 0) for resource in get_args(Resource)}
    return CivState(nations={player: Nation(stock=dict(stock)) for player in players})
