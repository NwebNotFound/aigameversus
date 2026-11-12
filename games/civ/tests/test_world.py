"""The hex map: distances on it, and what a generated map guarantees every nation."""

import json
import random
from collections import Counter
from itertools import combinations

import pytest

from games.civ.data_loader import CivData, load_civ_data
from games.civ.world import Hex, WorldMap, distance, generate_map

DATA = load_civ_data()
NATIONS = {4: ["ada", "bo", "cy", "di"], 5: ["ada", "bo", "cy", "di", "ed"]}
NATIONS[6] = [*NATIONS[5], "flo"]
EVERY_SIZE_AND_SEED = [(count, seed) for count in NATIONS for seed in range(40)]


def new_map(count: int = 4, seed: int = 1, data: CivData = DATA) -> WorldMap:
    return generate_map(NATIONS[count], data, random.Random(seed))


def with_map(**changes) -> CivData:
    """The shipped data with other numbers under `map` in balance.yaml."""
    balance = DATA.balance.model_copy(update={"map": DATA.balance.map.model_copy(update=changes)})
    return DATA.model_copy(update={"balance": balance})


def touching(world: WorldMap, tile: Hex) -> list[Hex]:
    return [other for other in world.tiles() if distance(tile, other) == 1]


def start_region(world: WorldMap, capital: Hex) -> list[Hex]:
    return [tile for tile in world.tiles() if distance(capital, tile) <= 1]


def is_land(world: WorldMap, tile: Hex) -> bool:
    return DATA.terrain[world.terrain(tile)].movement_cost is not None


def region_yields(world: WorldMap, capital: Hex) -> Counter:
    total = Counter()
    for tile in touching(world, capital):
        total.update(DATA.terrain[world.terrain(tile)].yields)
    return total


def test_tile_touches_the_six_tiles_around_it_and_odd_rows_sit_to_the_right():
    world = new_map()

    assert touching(world, (1, 1)) == [(1, 0), (2, 0), (0, 1), (2, 1), (1, 2), (2, 2)]
    assert touching(world, (1, 2)) == [(0, 1), (1, 1), (0, 2), (2, 2), (0, 3), (1, 3)]
    # At the rim there are fewer.
    assert touching(world, (0, 0)) == [(1, 0), (0, 1)]
    assert touching(world, (9, 5)) == [(9, 4), (8, 5)]


@pytest.mark.parametrize(
    ("a", "b", "steps"),
    [
        ((3, 2), (3, 2), 0),
        ((0, 0), (4, 0), 4),
        ((0, 0), (0, 2), 2),
        ((0, 0), (1, 2), 2),
        ((1, 1), (0, 0), 2),
        ((0, 1), (1, 0), 1),
        ((0, 0), (9, 5), 12),
    ],
)
def test_distance_is_the_number_of_steps(a, b, steps):
    assert distance(a, b) == distance(b, a) == steps


def test_distance_is_the_shortest_walk_over_touching_tiles():
    world = new_map(6)
    origin = (4, 3)
    walked, edge = {origin: 0}, [origin]
    for here in edge:  # breadth first
        for tile in touching(world, here):
            if tile not in walked:
                walked[tile] = walked[here] + 1
                edge.append(tile)

    assert walked == {tile: distance(origin, tile) for tile in world.tiles()}


def test_within_lists_the_tiles_up_to_a_radius_and_stops_at_the_rim():
    world = new_map()

    assert world.within((4, 2), 0) == [(4, 2)]
    assert len(world.within((4, 2), 1)) == 7
    assert len(world.within((4, 2), 2)) == 19
    assert world.within((0, 0), 1) == [(0, 0), (1, 0), (0, 1)]


@pytest.mark.parametrize(("count", "tiles"), [(4, 60), (5, 70), (6, 80)])
def test_map_grows_with_the_number_of_nations(count, tiles):
    world = new_map(count)

    assert len(world.tiles()) == tiles
    assert {len(row) for row in world.rows} == {10}
    assert {world.terrain(tile) for tile in world.tiles()} <= set(DATA.terrain)


def test_game_for_one_number_of_nations_gets_the_smallest_map():
    only_four = DATA.balance.map.nations.model_copy(update={"max": 4})

    assert len(new_map(data=with_map(nations=only_four)).tiles()) == 60


@pytest.mark.parametrize("players", [["ada", "bo", "cy"], [*NATIONS[6], "gus"]])
def test_wrong_number_of_nations_is_refused(players):
    with pytest.raises(ValueError, match=f"for 4 to 6 nations, got {len(players)}"):
        generate_map(players, DATA, random.Random(1))


@pytest.mark.parametrize("count", NATIONS)
def test_same_seed_gives_the_same_map(count):
    assert new_map(count, seed=5) == new_map(count, seed=5)


def test_seeds_give_different_maps_and_seats_do_not_fix_the_place():
    worlds = [new_map(seed=seed) for seed in range(10)]

    assert len({json.dumps(world.rows) for world in worlds}) == 10
    assert len({world.starts[0].tile for world in worlds}) > 3
    assert len({world.starts[0].scarce for world in worlds}) > 1


def test_seat_order_does_not_decide_who_starts_far_from_whom():
    # The capitals are found one after the other, the second as far from the first as possible.
    # Seats must not follow that order.
    first_two_farthest = 0
    for seed in range(40):
        first, second, *others = new_map(6, seed).starts
        gap = distance(first.tile, second.tile)
        first_two_farthest += all(gap >= distance(first.tile, other.tile) for other in others)

    assert 0 < first_two_farthest < 30


def test_map_does_not_depend_on_the_order_of_keys_in_the_data():
    balance = DATA.balance.map
    backwards = with_map(
        terrain_weights=dict(reversed(balance.terrain_weights.items())),
        rare_tiles=dict(reversed(balance.rare_tiles.items())),
        start_regions=dict(reversed(balance.start_regions.items())),
    )

    assert backwards == DATA
    assert new_map(seed=4, data=backwards) == new_map(seed=4)


def test_map_survives_storage_as_json_with_any_key_order():
    world = new_map(5, seed=3)

    def reverse_keys(value):
        if isinstance(value, dict):
            return {key: reverse_keys(value[key]) for key in reversed(value)}
        return [reverse_keys(item) for item in value] if isinstance(value, list) else value

    stored = reverse_keys(json.loads(json.dumps(world.model_dump())))

    assert WorldMap.model_validate(stored) == world


@pytest.mark.parametrize(("count", "seed"), EVERY_SIZE_AND_SEED)
def test_every_nation_starts_with_an_equal_region_that_lacks_one_resource(count, seed):
    world = new_map(count, seed)
    balance = DATA.balance.map

    assert [start.player for start in world.starts] == NATIONS[count]
    for start in world.starts:
        ring = sorted(world.terrain(tile) for tile in touching(world, start.tile))
        assert world.terrain(start.tile) == balance.capital_terrain
        assert ring == sorted(balance.start_regions[start.scarce])
        assert sum(region_yields(world, start.tile).values()) == 12
        # Short of a resource: never more of it than a nation short of something else, and
        # less than at least one. Food is the soft one: a food-short region has as much food as
        # a gold- or iron-short one, less only than a wood-short one (D-138).
        mine = region_yields(world, start.tile)[start.scarce]
        theirs = [
            region_yields(world, other.tile)[start.scarce]
            for other in world.starts
            if other.scarce != start.scarce
        ]
        assert all(mine <= other for other in theirs) and mine < max(theirs)
        if start.scarce != "food":
            assert all(mine < other for other in theirs)
    # The shortages are spread over the resources as evenly as the number of nations allows.
    shortages = Counter(start.scarce for start in world.starts)
    assert len(shortages) == 4
    assert max(shortages.values()) - min(shortages.values()) <= 1


def test_start_region_is_laid_out_differently_from_map_to_map():
    east_of_the_capital = set()
    for seed in range(40):
        world = new_map(seed=seed)
        start = next(start for start in world.starts if start.scarce == "iron")
        east_of_the_capital.add(world.terrain((start.col + 1, start.row)))

    assert east_of_the_capital == {"plains", "forest", "river"}


@pytest.mark.parametrize(("count", "seed"), EVERY_SIZE_AND_SEED)
def test_start_regions_are_whole_and_apart(count, seed):
    world = new_map(count, seed)
    regions = [start_region(world, start.tile) for start in world.starts]

    assert all(len(region) == 7 for region in regions)  # none is cut off by the rim
    assert len({tile for region in regions for tile in region}) == 7 * count
    assert min(distance(a.tile, b.tile) for a, b in combinations(world.starts, 2)) >= 3


def test_capitals_are_spread_as_widely_as_the_map_allows():
    # Five capitals fit four steps apart on their map; a single careless draw rarely finds that.
    spreads = [
        min(distance(a.tile, b.tile) for a, b in combinations(new_map(5, seed).starts, 2))
        for seed in range(40)
    ]

    assert spreads.count(4) > 35


@pytest.mark.parametrize(("count", "seed"), EVERY_SIZE_AND_SEED)
def test_all_land_is_one_piece(count, seed):
    world = new_map(count, seed)
    land = {tile for tile in world.tiles() if is_land(world, tile)}
    reached, edge = {world.starts[0].tile}, [world.starts[0].tile]
    for here in edge:
        for tile in touching(world, here):
            if tile in land and tile not in reached:
                reached.add(tile)
                edge.append(tile)

    assert reached == land


@pytest.mark.parametrize(("count", "seed"), EVERY_SIZE_AND_SEED)
def test_rare_tiles_are_few_outside_the_start_regions_and_not_side_by_side(count, seed):
    world = new_map(count, seed)
    rare = [tile for tile in world.tiles() if DATA.terrain[world.terrain(tile)].rare]
    started = {tile for start in world.starts for tile in start_region(world, start.tile)}

    assert Counter(world.terrain(tile) for tile in rare) == {"iron_deposit": 2, "gold_vein": 2}
    assert not started & set(rare)
    assert all(distance(a, b) > 1 for a, b in combinations(rare, 2))


def two_nearest_capitals(world: WorldMap, tile: Hex) -> list[int]:
    return sorted(distance(tile, start.tile) for start in world.starts)[:2]


def test_rare_tiles_lie_between_nations_not_at_one_nations_door_or_in_a_far_corner():
    leads, rivals = Counter(), Counter()
    for count, seed in EVERY_SIZE_AND_SEED:
        world = new_map(count, seed)
        for tile in world.tiles():
            if DATA.terrain[world.terrain(tile)].rare:
                nearest, rival = two_nearest_capitals(world, tile)
                leads[rival - nearest] += 1
                rivals[rival] += 1

    # The nearest capital is at most one step closer than the next one.
    assert set(leads) <= {0, 1}
    assert leads[0] > 5 * leads[1]
    # And two nations are close: nearly always two steps away, just outside their regions.
    assert rivals[2] > 0.85 * sum(rivals.values())


def test_neither_rare_resource_always_gets_the_better_places():
    def worse_place(world: WorldMap, kind: str) -> tuple[int, int]:
        """How uneven and how far the two nearest capitals are, at the worse tile of that kind."""
        places = []
        for tile in world.tiles():
            if world.terrain(tile) == kind:
                nearest, rival = two_nearest_capitals(world, tile)
                places.append((rival - nearest, rival))
        return max(places)

    better = Counter()
    for seed in range(40):
        world = new_map(seed=seed)
        iron, gold = worse_place(world, "iron_deposit"), worse_place(world, "gold_vein")
        better["iron" if iron < gold else "gold" if gold < iron else "same"] += 1

    assert better["iron"] > 3
    assert better["gold"] > 3


def test_no_side_of_the_map_is_favoured():
    capitals, rare = [], []
    for count, seed in EVERY_SIZE_AND_SEED:
        world = new_map(count, seed)
        height = len(world.rows) - 1
        capitals += [(start.col / 9, start.row / height) for start in world.starts]
        rare += [
            (col / 9, row / height)
            for col, row in world.tiles()
            if DATA.terrain[world.terrain((col, row))].rare
        ]

    for places in (capitals, rare):
        for axis in (0, 1):
            assert 0.45 < sum(place[axis] for place in places) / len(places) < 0.55


def test_many_rare_tiles_still_stay_out_of_the_start_regions():
    world = new_map(data=with_map(rare_tiles={"iron_deposit": 6, "gold_vein": 6}))
    started = {tile for start in world.starts for tile in start_region(world, start.tile)}
    rare = {tile for tile in world.tiles() if DATA.terrain[world.terrain(tile)].rare}

    assert len(rare) == 12
    assert not started & rare


def test_terrain_outside_the_start_regions_follows_the_weights():
    seen = Counter()
    for count, seed in EVERY_SIZE_AND_SEED:
        world = new_map(count, seed)
        started = {tile for start in world.starts for tile in start_region(world, start.tile)}
        seen.update(world.terrain(tile) for tile in world.tiles() if tile not in started)

    common = {kind: seen[kind] / sum(seen.values()) for kind in DATA.balance.map.terrain_weights}
    assert common["plains"] > common["forest"] > common["hills"] > common["river"] > 0.05
    assert 0.1 < common["mountains"] + common["water"] < 0.25


def test_map_that_cannot_hold_the_capitals_is_refused():
    with pytest.raises(ValueError, match="6 rows of 5 tiles have no room for 4 capitals"):
        new_map(data=with_map(width=5, tiles=DATA.balance.map.tiles.model_copy(update={"min": 30})))


def test_weights_that_leave_no_connected_land_are_refused():
    with pytest.raises(ValueError, match="no map with all land in one piece"):
        new_map(data=with_map(terrain_weights={"water": 1}))


def test_rare_tiles_without_room_are_refused():
    with pytest.raises(ValueError, match="room for the rare tiles"):
        new_map(data=with_map(rare_tiles={"iron_deposit": 40, "gold_vein": 2}))


def test_start_region_is_as_large_as_the_land_a_capital_works():
    balance = DATA.balance
    regions = {resource: ring * 3 for resource, ring in balance.map.start_regions.items()}
    larger = DATA.model_copy(
        update={
            "balance": balance.model_copy(
                update={
                    "city": balance.city.model_copy(update={"work_radius": 2}),
                    "map": balance.map.model_copy(
                        update={
                            "width": 14,
                            "tiles": balance.map.tiles.model_copy(update={"min": 140, "max": 140}),
                            "start_regions": regions,
                        }
                    ),
                }
            )
        }
    )

    world = new_map(data=larger)

    worked = [world.within(start.tile, 2) for start in world.starts]
    assert all(len(region) == 19 for region in worked)
    assert len({tile for region in worked for tile in region}) == 4 * 19
    for start, region in zip(world.starts, worked, strict=True):
        ring = sorted(world.terrain(tile) for tile in region if tile != start.tile)
        assert ring == sorted(regions[start.scarce])
