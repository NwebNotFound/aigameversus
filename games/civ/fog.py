"""Fog of war: which tiles a nation sees, and the map as it sees it.

A nation sees the tiles around its viewpoints, its cities and armies. How far
each of them sees is the caller's business: ``map.fog_vision_radius`` in
``data/balance.yaml``, plus what a watchtower or a scout adds.

    seen = visible_tiles(world, [(capital, 2), (scout_army, 4)])
    map_view(world, seen)  # rows of terrain ids, None under the fog
"""

from __future__ import annotations

from collections.abc import Collection, Iterable

from games.civ.world import Hex, WorldMap


def visible_tiles(world: WorldMap, viewpoints: Iterable[tuple[Hex, int]]) -> set[Hex]:
    """Every tile within the radius of at least one ``(tile, radius)`` viewpoint."""
    return {tile for center, radius in viewpoints for tile in world.within(center, radius)}


def map_view(world: WorldMap, visible: Collection[Hex]) -> list[list[str | None]]:
    """The map for one nation's observation: the terrain of visible tiles, None for the rest."""
    return [
        [kind if (col, row) in visible else None for col, kind in enumerate(line)]
        for row, line in enumerate(world.rows)
    ]
