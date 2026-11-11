"""The state of a Throne of Tokens match, as far as the game is built.

It holds what is true now and no rules. It changes only when an event is
applied (``apply_event`` in ``turn.py``), so the event log of a match rebuilds
it exactly.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, get_args

from pydantic import BaseModel

from games.civ.data_loader import CivData, Focus, Resource
from games.civ.world import Hex, WorldMap

Stock = dict[Resource, int]
NEUTRAL = "neutral"  # the owner of rebel cities and barbarian armies: at war with everyone


class Nation(BaseModel):
    stock: Stock  # what the nation owns of every resource; never below 0
    hungry_rounds: int = 0  # rounds in a row in which upkeep was not paid in full
    reputation: int = 50  # public, between the limits in treaties.yaml; new_game sets the start


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
    conquered_round: int | None = None  # the round it was last conquered (combat sets it)

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
    moved_in_round: int | None = None  # the round of its last move; an army moves once a round

    @property
    def tile(self) -> Hex:
        return self.col, self.row


class Pact(BaseModel):
    """A treaty in force between two nations."""

    id: str  # "t1", "t2", ... in the order treaties were signed
    kind: str  # a treaty id from the data
    parties: list[str]  # the two nations, sorted
    ends_round: int | None = None  # the last round it holds; None: until broken
    payer: str | None = None  # a tribute: who pays `payment` to the other every round
    payment: dict[Resource, int] = {}


class Offer(BaseModel):
    """A treaty or trade one nation offered another, open until answered or the round ends."""

    id: str  # "o1", "o2", ... in the order offers were made
    sender: str
    to: str
    round: int  # offered in this round; it lapses when the next one starts
    treaty: str | None = None  # a treaty offer: the treaty id; None: a trade offer
    rounds: int | None = None  # how long the treaty or trade runs; None: until broken
    payer: str | None = None
    payment: dict[Resource, int] = {}
    gives: dict[Resource, int] = {}  # a trade: what the sender hands over every round
    wants: dict[Resource, int] = {}  # and what it gets for it


class Deal(BaseModel):
    """An accepted trade, carried out in the trade step of each round until it is done."""

    id: str  # the id of the offer it came from
    sender: str
    to: str
    gives: dict[Resource, int]
    wants: dict[Resource, int]
    rounds_left: int


class Condition(BaseModel):
    """A lasting effect of a random event on the cities around a tile, such as a drought."""

    event: str
    col: int
    row: int
    radius: int
    until_round: int  # the last round it holds
    modifiers: dict[Resource, float]  # relative change of a city's yield, -0.5 = half


class CivState(BaseModel):
    round: int = 0  # the round being played; 0 before the first
    world: WorldMap = WorldMap(rows=[], starts=[])
    nations: dict[str, Nation]
    cities: list[City] = []  # in founding order: the older city wins a tie over a tile
    armies: list[Army] = []
    armies_raised: int = 0  # how many armies there have ever been, for the next id
    treaties: list[Pact] = []
    treaties_signed: int = 0  # for the next treaty id
    offers: list[Offer] = []
    offers_made: int = 0  # for the next offer id
    deals: list[Deal] = []
    wars: list[list[str]] = []  # pairs of nations at war, each sorted
    conditions: list[Condition] = []  # from random events, oldest first
    rich_rounds: dict[str, int] = {}  # rounds in a row a nation held the economic-victory gold
    victory: dict[str, Any] | None = None  # {kind, winners, placements} once the match is won

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
    reputation = data.reputation.start
    return CivState(
        nations={player: Nation(stock=dict(stock), reputation=reputation) for player in players}
    )
