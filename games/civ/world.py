"""The hex map of Throne of Tokens: its shape, and how a new one is made.

A tile is ``(col, row)``. Rows run left to right and odd rows sit half a tile
to the right, so every tile inside the map touches six others:

     (0,0) (1,0) (2,0)
        (0,1) (1,1) (2,1)
     (0,2) (1,2) (2,2)

    world = generate_map(["p1", "p2", "p3", "p4"], load_civ_data(), rng)
    world.terrain((3, 2))  # "forest"
    world.starts[0]  # Start(player="p1", col=7, row=4, scarce="iron")

All numbers come from ``data/balance.yaml`` (``map``) and ``data/terrain.yaml``.
"""

from __future__ import annotations

import random
from collections.abc import Sequence
from itertools import combinations
from typing import get_args

from pydantic import BaseModel

from games.civ.data_loader import CivData, Resource

Hex = tuple[int, int]

_CAPITAL_DRAWS = 20  # the most widely spread of these becomes the layout
_TERRAIN_DRAWS = 200  # before the data is called unusable


def distance(a: Hex, b: Hex) -> int:
    """Steps from one tile to the other on an empty map."""
    (aq, ar), (bq, br) = _axial(a), _axial(b)
    return (abs(aq - bq) + abs(ar - br) + abs(aq + ar - bq - br)) // 2


def _axial(tile: Hex) -> Hex:
    col, row = tile
    return col - (row - row % 2) // 2, row


class Start(BaseModel):
    """Where a nation begins: the tile of its capital."""

    player: str
    col: int
    row: int
    scarce: Resource  # the resource its start region is short of

    @property
    def tile(self) -> Hex:
        return self.col, self.row


class WorldMap(BaseModel):
    rows: list[list[str]]  # terrain id of each tile: rows[row][col]
    starts: list[Start]  # in the order of the players

    def tiles(self) -> list[Hex]:
        return [(col, row) for row, line in enumerate(self.rows) for col in range(len(line))]

    def terrain(self, tile: Hex) -> str:
        col, row = tile
        return self.rows[row][col]

    def within(self, center: Hex, radius: int) -> list[Hex]:
        """The tiles of the map at most `radius` steps from `center`, the center included."""
        return [tile for tile in self.tiles() if distance(center, tile) <= radius]


def generate_map(players: Sequence[str], data: CivData, rng: random.Random) -> WorldMap:
    """Make the map for a match. The same players, data and random stream give the same map.

    Starts are fair in three ways. Every capital works the same number of
    tiles with the same total yield and is short of one resource. Capitals are
    spread as far apart as the map allows, and no two start regions share a
    tile. All land is one piece, so every nation can reach every other.
    """
    balance = data.balance.map
    nations = balance.nations
    if not nations.min <= len(players) <= nations.max:
        raise ValueError(
            f"Throne of Tokens is for {nations.min} to {nations.max} nations, got {len(players)}"
        )
    grown = (len(players) - nations.min) / max(nations.max - nations.min, 1)
    tiles = balance.tiles.min + grown * (balance.tiles.max - balance.tiles.min)
    height = round(tiles / balance.width)
    world = WorldMap(rows=[[""] * balance.width for _ in range(height)], starts=[])

    capitals = _place_capitals(world, len(players), data.balance.city.work_radius, rng)
    rng.shuffle(capitals)
    scarce = sorted(get_args(Resource))
    rng.shuffle(scarce)
    world.starts = [
        Start(player=player, col=col, row=row, scarce=scarce[seat % len(scarce)])
        for seat, (player, (col, row)) in enumerate(zip(players, capitals, strict=True))
    ]

    for _ in range(_TERRAIN_DRAWS):
        if _lay_terrain(world, data, rng):
            return world
    raise ValueError(
        "balance.yaml: map: no map with all land in one piece and room for the rare tiles "
        f"in {_TERRAIN_DRAWS} draws; lower the weights of impassable terrain"
    )


def _place_capitals(world: WorldMap, count: int, work_radius: int, rng: random.Random) -> list[Hex]:
    """Capitals whose start regions lie on the map and apart, spread as widely as a greedy pick can.

    The first is drawn at random; each further one is the tile farthest from
    those already chosen. Of several draws the most widely spread wins.
    """
    region = 1 + 3 * work_radius * (work_radius + 1)
    inland = [tile for tile in world.tiles() if len(world.within(tile, work_radius)) == region]
    best: list[Hex] = []
    best_spread = 2 * work_radius  # regions of capitals this close would share a tile
    for _ in range(_CAPITAL_DRAWS):
        chosen = rng.sample(inland, min(1, len(inland)))
        while 0 < len(chosen) < count:
            chosen.append(max(inland, key=lambda tile: min(distance(tile, c) for c in chosen)))
        spread = min((distance(a, b) for a, b in combinations(chosen, 2)), default=0)
        if spread > best_spread:
            best, best_spread = chosen, spread
    if not best:
        raise ValueError(
            f"balance.yaml: map: {len(world.rows)} rows of {len(world.rows[0])} tiles have no room "
            f"for {count} capitals with separate start regions"
        )
    return best


def _lay_terrain(world: WorldMap, data: CivData, rng: random.Random) -> bool:
    """Draw the terrain of every tile. False when the draw gave a map that cannot be played."""
    balance = data.balance.map
    kinds = sorted(balance.terrain_weights)
    weights = [balance.terrain_weights[kind] for kind in kinds]
    for row in world.rows:
        row[:] = rng.choices(kinds, weights, k=len(row))

    regions: set[Hex] = set()
    for start in world.starts:
        ring = [
            t for t in world.within(start.tile, data.balance.city.work_radius) if t != start.tile
        ]
        around = list(balance.start_regions[start.scarce])
        rng.shuffle(around)
        for (col, row), kind in zip(ring, around, strict=True):
            world.rows[row][col] = kind
        world.rows[start.row][start.col] = balance.capital_terrain
        regions.update(ring, [start.tile])

    # Rare tiles go between nations: where the nearest capital has the smallest lead over the
    # second nearest, then where that rival is close. Never two side by side.
    capitals = [start.tile for start in world.starts]

    def contested(tile: Hex) -> tuple[int, int]:
        nearest, rival = sorted(distance(tile, capital) for capital in capitals)[:2]
        return rival - nearest, rival

    free = [tile for tile in _land(world, data) if tile not in regions]
    rng.shuffle(free)
    free.sort(key=contested)
    rare = [kind for kind in sorted(balance.rare_tiles) for _ in range(balance.rare_tiles[kind])]
    rng.shuffle(rare)
    placed: list[Hex] = []
    for kind in rare:
        spot = next((t for t in free if all(distance(t, p) > 1 for p in placed)), None)
        if spot is None:
            return False
        world.rows[spot[1]][spot[0]] = kind
        placed.append(spot)

    return _in_one_piece(_land(world, data))


def _land(world: WorldMap, data: CivData) -> list[Hex]:
    return [t for t in world.tiles() if data.terrain[world.terrain(t)].movement_cost is not None]


def _in_one_piece(land: list[Hex]) -> bool:
    reached, edge = {land[0]}, [land[0]]
    while edge:
        here = edge.pop()
        for tile in land:
            if tile not in reached and distance(here, tile) == 1:
                reached.add(tile)
                edge.append(tile)
    return len(reached) == len(land)
