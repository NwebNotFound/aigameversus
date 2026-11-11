"""Fog of war: a nation sees the tiles around its cities and armies, and nothing else."""

import random

import pytest

from games.civ.data_loader import load_civ_data
from games.civ.fog import map_view, visible_tiles
from games.civ.world import WorldMap, distance, generate_map

DATA = load_civ_data()
SIGHT = DATA.balance.map.fog_vision_radius
PLAYERS = ["ada", "bo", "cy", "di", "ed", "flo"]


@pytest.fixture
def world() -> WorldMap:
    return generate_map(PLAYERS[:4], DATA, random.Random(2))


def test_viewpoint_sees_every_tile_within_its_radius(world):
    seen = visible_tiles(world, [((4, 2), 2)])

    assert len(seen) == 19
    assert seen == {tile for tile in world.tiles() if distance((4, 2), tile) <= 2}


def test_sight_ends_at_the_rim_of_the_map(world):
    assert visible_tiles(world, [((0, 0), 1)]) == {(0, 0), (1, 0), (0, 1)}


def test_nation_sees_what_any_of_its_viewpoints_sees(world):
    city, army, scout = ((1, 1), 2), ((8, 4), 2), ((5, 3), 4)

    seen = visible_tiles(world, [city, army, scout])

    assert seen == visible_tiles(world, [city]) | visible_tiles(world, [army]) | visible_tiles(
        world, [scout]
    )
    # A viewpoint that sees farther, like a scout, shows more.
    assert len(visible_tiles(world, [scout])) > len(visible_tiles(world, [((5, 3), 2)]))


def test_nation_without_cities_and_armies_sees_nothing(world):
    assert visible_tiles(world, []) == set()
    assert map_view(world, set()) == [[None] * 10 for _ in range(6)]


def test_map_view_shows_terrain_only_where_the_nation_sees(world):
    seen = visible_tiles(world, [((4, 2), SIGHT)])

    view = map_view(world, seen)

    for col, row in world.tiles():
        assert view[row][col] == (world.terrain((col, row)) if (col, row) in seen else None)


def test_map_view_does_not_depend_on_what_lies_under_the_fog(world):
    seen = visible_tiles(world, [((4, 2), SIGHT)])
    other = world.model_copy(deep=True)
    for col, row in other.tiles():
        if (col, row) not in seen:
            other.rows[row][col] = "water" if other.rows[row][col] != "water" else "plains"

    assert other != world
    assert map_view(other, seen) == map_view(world, seen)


def test_map_view_is_a_copy(world):
    view = map_view(world, set(world.tiles()))
    assert view == world.rows

    view[0][0] = "changed"

    assert world.terrain((0, 0)) != "changed"


@pytest.mark.parametrize("count", [4, 5, 6])
@pytest.mark.parametrize("seed", range(40))
def test_at_the_start_a_nation_sees_its_region_and_no_other_capital(count, seed):
    world = generate_map(PLAYERS[:count], DATA, random.Random(seed))

    for start in world.starts:
        seen = visible_tiles(world, [(start.tile, SIGHT)])
        assert set(world.within(start.tile, DATA.balance.city.work_radius)) <= seen
        assert not seen & {other.tile for other in world.starts if other is not start}
