"""Armies: the starting units, training, moving, splitting, merging, settling and starving."""

import random

import pytest

from games.civ.armies import (
    army_viewpoints,
    deploy_start_units,
    disband,
    disband_problem,
    merge,
    merge_problem,
    move,
    move_problem,
    movement,
    reachable,
    settle,
    settle_problem,
    split,
    split_problem,
    train,
    train_problem,
    training_cost,
)
from games.civ.economy import found_city
from games.civ.tests.realm import (
    CENTER,
    DATA,
    PLAYERS,
    RICH,
    RING,
    Realm,
    bare_map,
    flat_map,
    with_balance,
)
from games.civ.world import distance, generate_map


def within(realm: Realm, center, steps: int) -> set:
    return {tile for tile in realm.state.world.tiles() if 0 < distance(center, tile) <= steps}


@pytest.fixture
def realm() -> Realm:
    """Plains everywhere; ada has the city c1 at CENTER and all she needs."""
    realm = Realm(flat_map("plains"))
    realm.found("ada", CENTER)
    realm.state.nations["ada"].stock = dict(RICH)
    return realm


# --- the start ----------------------------------------------------------------


@pytest.mark.parametrize("count", [4, 5, 6])
def test_every_nation_starts_with_a_spearman_and_a_settler_on_its_capital(count):
    players = PLAYERS[:count]
    realm = Realm(generate_map(players, DATA, random.Random(count)), players)
    for start in realm.state.world.starts:
        found_city(realm.state, realm.ctx, start.player, start.tile)

    deploy_start_units(realm.state, DATA, realm.ctx)

    assert [army.id for army in realm.state.armies] == [f"a{n}" for n in range(1, count + 1)]
    for army, start in zip(realm.state.armies, realm.state.world.starts, strict=True):
        assert (army.owner, army.tile) == (start.player, start.tile)
        assert realm.units(army.id) == ["spearman", "settler"]
        assert realm.stock(army.owner) == {"food": 5, "wood": 5, "iron": 0, "gold": 5}


def test_starting_units_come_from_the_data():
    scouts = [
        group.model_copy(update={"unit": "scout", "count": 3})
        for group in DATA.balance.start.units[:1]
    ]
    data = with_balance("start", units=scouts)
    realm = Realm(generate_map(PLAYERS[:4], data, random.Random(1)), PLAYERS[:4], data)

    deploy_start_units(realm.state, data, realm.ctx)

    assert [realm.units(army.id) for army in realm.state.armies] == [["scout"] * 3] * 4


# --- movement -----------------------------------------------------------------


def test_army_is_as_fast_as_its_slowest_unit(realm):
    riders = realm.state.army(realm.army("ada", CENTER, "horseman", "scout"))
    mixed = realm.state.army(realm.army("ada", CENTER, "horseman", "spearman", "scout"))

    assert (movement(DATA, riders), movement(DATA, mixed)) == (3, 1)


def test_slow_army_reaches_the_tiles_next_to_it_whatever_they_cost():
    kinds = ["forest", "hills", "river", "iron_deposit", "mountains", "water"]
    realm = Realm(flat_map("plains", dict(zip(RING, kinds, strict=True))))
    army = realm.army("ada", CENTER, "spearman")

    ways = reachable(realm.state, DATA, army)

    assert ways == {tile: [tile] for tile in RING[:4]}  # not onto mountains or water


def test_fast_army_gets_three_tiles_far_on_plains(realm):
    army = realm.army("ada", CENTER, "horseman")

    ways = reachable(realm.state, DATA, army)

    assert set(ways) == within(realm, CENTER, 3)
    for tile, path in ways.items():
        assert path[-1] == tile
        assert len(path) == distance(CENTER, tile)
        for a, b in zip([CENTER, *path], path, strict=False):
            assert distance(a, b) == 1


def test_costly_terrain_shortens_the_way_but_a_last_step_is_always_possible():
    realm = Realm(flat_map("plains", dict.fromkeys(RING, "forest")))
    army = realm.army("ada", CENTER, "horseman")

    # Forest costs 2 of 3 points; the point left is enough for one more tile.
    assert set(reachable(realm.state, DATA, army)) == within(realm, CENTER, 2)

    hills = Realm(flat_map("plains", {(6, 2): "hills"}))
    army = hills.army("ada", CENTER, "horseman")
    assert (6, 2) in reachable(hills.state, DATA, army)  # entered with 1 point for a cost of 2


def test_leaving_a_river_costs_one_more():
    target = (6, 2)  # three tiles along the row; the only shortest way is over (4, 2)
    dry = Realm(flat_map("plains"))
    assert target in reachable(dry.state, DATA, dry.army("ada", CENTER, "horseman"))

    wet = Realm(flat_map("plains", {(4, 2): "river"}))
    ways = reachable(wet.state, DATA, wet.army("ada", CENTER, "horseman"))
    assert target not in ways
    assert ways[(5, 2)] == [(4, 2), (5, 2)]

    on_river = Realm(flat_map("plains", {CENTER: "river"}))
    army = on_river.army("ada", CENTER, "horseman")
    assert set(reachable(on_river.state, DATA, army)) == within(on_river, CENTER, 2)


@pytest.mark.parametrize(
    ("forest", "path"),
    [((4, 2), [(3, 3), (4, 3)]), ((3, 3), [(4, 2), (4, 3)])],
)
def test_of_two_ways_the_army_takes_the_one_that_costs_less(forest, path):
    realm = Realm(flat_map("plains", {forest: "forest"}))
    army = realm.army("ada", CENTER, "horseman")

    assert reachable(realm.state, DATA, army)[(4, 3)] == path


def test_army_walks_around_what_it_cannot_cross():
    realm = Realm(flat_map("plains", {(4, 2): "mountains"}))
    army = realm.army("ada", CENTER, "horseman")

    ways = reachable(realm.state, DATA, army)

    assert (4, 2) not in ways
    assert (5, 2) in ways
    assert (4, 2) not in ways[(5, 2)]
    assert (6, 2) not in ways  # the detour is one tile too long


def test_moving_puts_the_army_on_the_tile_and_logs_its_way(realm):
    army = realm.army("ada", CENTER, "horseman")

    move(realm.state, DATA, realm.ctx, "ada", army, (5, 2))

    assert realm.state.army(army).tile == (5, 2)
    assert realm.of_type("army_moved") == [{"army": army, "path": [[4, 2], [5, 2]]}]


def test_move_beyond_reach_is_refused_with_the_tiles_in_reach(realm):
    army = realm.army("ada", (0, 0), "spearman")

    assert move_problem(realm.state, DATA, "ada", army, (1, 0)) is None
    assert move_problem(realm.state, DATA, "ada", army, (2, 0)) == (
        "a1 cannot reach (2, 0) this round. It can move to: (0, 1), (1, 0)."
    )
    assert move_problem(realm.state, DATA, "ada", army, (0, 0)) is not None  # where it stands


def test_army_of_another_nation_cannot_be_ordered_and_is_not_given_away(realm):
    realm.army("ada", CENTER, "spearman")
    theirs = realm.army("bo", (0, 0), "spearman")

    for army_id in [theirs, "a9"]:
        assert move_problem(realm.state, DATA, "ada", army_id, (1, 0)) == (
            f"You have no army '{army_id}'. Your armies: a1."
        )
    assert disband_problem(realm.state, "ada", theirs) is not None
    assert split_problem(realm.state, "ada", theirs, ["spearman"]) is not None
    assert settle_problem(realm.state, DATA, "ada", theirs) is not None
    assert merge_problem(realm.state, DATA, "ada", ["a1", theirs]) == (
        "You have no army 'a2'. Your armies: a1."
    )


def test_armies_of_two_nations_can_pass_each_other_and_share_a_tile(realm):
    ours = realm.army("ada", (2, 2), "spearman")
    theirs = realm.army("bo", (3, 2), "spearman")

    move(realm.state, DATA, realm.ctx, "ada", ours, (3, 2))
    move(realm.state, DATA, realm.ctx, "bo", theirs, (2, 2))
    assert (realm.state.army(ours).tile, realm.state.army(theirs).tile) == ((3, 2), (2, 2))

    move(realm.state, DATA, realm.ctx, "bo", theirs, (3, 2))
    assert realm.state.army(ours).tile == realm.state.army(theirs).tile


# --- training -----------------------------------------------------------------


def test_trained_units_are_paid_for_and_stand_in_the_city_as_a_new_army(realm):
    army = train(realm.state, DATA, realm.ctx, "ada", "c1", "spearman", 3)

    assert army == "a1"
    assert realm.state.army(army).tile == CENTER
    assert realm.units(army) == ["spearman"] * 3
    assert realm.stock() == {"food": 96, "wood": 93, "iron": 99, "gold": 99}
    assert realm.of_type("army_raised") == [
        {
            "army": "a1",
            "owner": "ada",
            "col": 3,
            "row": 2,
            "units": [{"kind": "spearman", "bonus": 0}] * 3,
            "cost": {"wood": 6, "food": 3},
        }
    ]
    assert train(realm.state, DATA, realm.ctx, "ada", "c1", "scout", 1) == "a2"


def test_most_units_need_a_barracks_in_the_city(realm):
    for anywhere in ["spearman", "settler", "scout"]:
        assert train_problem(realm.state, DATA, "ada", "c1", anywhere, 1) is None
    for unit in ["swordsman", "horseman", "archer", "siege_engine"]:
        assert train_problem(realm.state, DATA, "ada", "c1", unit, 1) == (
            f"A {unit} is trained in a barracks, and c1 has none. "
            "Build one there or train in a city that has one."
        )

    realm.build("ada", "c1", "barracks")
    assert train_problem(realm.state, DATA, "ada", "c1", "archer", 1) is not None  # not finished
    realm.round()
    assert train_problem(realm.state, DATA, "ada", "c1", "archer", 1) is None


@pytest.mark.parametrize(
    ("unit", "count", "cost"),
    [
        ("swordsman", 1, {"iron": 3, "food": 1}),  # 2.4 and 0.8, rounded up
        ("swordsman", 2, {"iron": 5, "food": 2}),
        ("swordsman", 5, {"iron": 12, "food": 4}),
        ("spearman", 5, {"wood": 8, "food": 4}),
        ("settler", 1, {"food": 5, "wood": 2}),
    ],
)
def test_barracks_takes_a_fifth_off_the_order_rounded_up(unit, count, cost):
    realm = Realm(flat_map("plains"))
    realm.found("ada", CENTER, "barracks")
    realm.found("ada", (0, 0))

    assert training_cost(realm.state, DATA, "c1", unit, count) == cost
    full = {resource: amount * count for resource, amount in DATA.units[unit].cost.items()}
    assert training_cost(realm.state, DATA, "c2", unit, count) == full


def test_forge_makes_the_units_trained_there_stronger_but_not_settlers():
    realm = Realm(flat_map("plains"))
    realm.found("ada", CENTER, "barracks", "forge")
    realm.found("ada", (0, 0), "barracks")
    realm.state.nations["ada"].stock = dict(RICH)

    forged = train(realm.state, DATA, realm.ctx, "ada", "c1", "swordsman", 2)
    settlers = train(realm.state, DATA, realm.ctx, "ada", "c1", "settler", 1)
    plain = train(realm.state, DATA, realm.ctx, "ada", "c2", "swordsman", 1)

    assert [troop.bonus for troop in realm.state.army(forged).units] == [1, 1]
    assert [troop.bonus for troop in realm.state.army(settlers).units] == [0]
    assert [troop.bonus for troop in realm.state.army(plain).units] == [0]


def test_training_that_cannot_be_paid_is_refused_with_cost_and_stock():
    realm = Realm(flat_map("plains"))
    realm.found("ada", CENTER, "barracks")

    assert train_problem(realm.state, DATA, "ada", "c1", "spearman", 2) is None
    assert train_problem(realm.state, DATA, "ada", "c1", "swordsman", 2) == (
        "2 swordsman cost 2 food, 5 iron; you have 5 food, 0 iron."
    )


def test_one_order_trains_one_army_of_a_known_unit_in_an_own_city(realm):
    assert train_problem(realm.state, DATA, "ada", "c1", "spearman", 10) is None
    for count in [0, -1, 11]:
        assert train_problem(realm.state, DATA, "ada", "c1", "spearman", count) == (
            f"One order trains 1 to 10 units, not {count}."
        )
    assert train_problem(realm.state, DATA, "ada", "c1", "knight", 1) == (
        "There is no unit 'knight'. Units: spearman, swordsman, horseman, archer, "
        "siege_engine, settler, scout."
    )
    assert train_problem(realm.state, DATA, "bo", "c1", "spearman", 1) == (
        "You have no city 'c1'. Your cities: none."
    )


# --- organising ---------------------------------------------------------------


def test_split_takes_the_first_units_of_each_kind_into_a_new_army(realm):
    army = realm.army("ada", CENTER, "spearman", "archer", "spearman", "settler")

    new = split(realm.state, realm.ctx, "ada", army, ["settler", "spearman"])

    assert new == "a2"
    assert realm.units(army) == ["archer", "spearman"]
    assert realm.units(new) == ["spearman", "settler"]
    assert realm.state.army(new).tile == CENTER
    assert realm.of_type("army_split") == [{"army": "a1", "indexes": [0, 3], "new_army": "a2"}]


def test_split_must_name_units_the_army_has_and_leave_one_behind(realm):
    army = realm.army("ada", CENTER, "spearman", "archer", "spearman")

    assert split_problem(realm.state, "ada", army, ["spearman", "spearman"]) is None
    assert split_problem(realm.state, "ada", army, []) == (
        "Name the units to split off, for example ['spearman', 'spearman']."
    )
    assert split_problem(realm.state, "ada", army, ["archer", "archer"]) == (
        "a1 has 1 archer, not 2. Its units: spearman, archer, spearman."
    )
    assert split_problem(realm.state, "ada", army, ["scout"]) == (
        "a1 has 0 scout, not 1. Its units: spearman, archer, spearman."
    )
    assert split_problem(realm.state, "ada", army, ["spearman", "archer", "spearman"]) == (
        "A split must leave a unit behind, and these are all of a1."
    )


def test_split_can_take_several_units_of_one_kind(realm):
    army = realm.army("ada", CENTER, "spearman", "archer", "spearman", "spearman")

    new = split(realm.state, realm.ctx, "ada", army, ["spearman", "spearman"])

    assert (realm.units(army), realm.units(new)) == (["archer", "spearman"], ["spearman"] * 2)


def test_merge_joins_the_armies_into_the_first_and_keeps_every_unit(realm):
    first = realm.army("ada", CENTER, "spearman", bonus=1)
    second = realm.army("ada", CENTER, "archer", "scout")
    third = realm.army("ada", CENTER, "spearman")

    merge(realm.state, DATA, realm.ctx, "ada", [second, first, third])

    assert [army.id for army in realm.state.armies] == [second]
    merged = realm.state.army(second).units
    assert [(troop.kind, troop.bonus) for troop in merged] == [
        ("archer", 0),
        ("scout", 0),
        ("spearman", 1),
        ("spearman", 0),
    ]
    # A split takes the first of a kind: here the one from the forge.
    new = split(realm.state, realm.ctx, "ada", second, ["spearman"])
    assert [(troop.kind, troop.bonus) for troop in realm.state.army(new).units] == [("spearman", 1)]
    assert new == "a4"  # the ids of the merged armies are not used again


def test_merge_needs_different_own_armies_on_one_tile_with_ten_units_at_most(realm):
    six = realm.army("ada", CENTER, *["spearman"] * 6)
    four = realm.army("ada", CENTER, *["archer"] * 4)
    one = realm.army("ada", CENTER, "scout")
    away = realm.army("ada", (4, 2), "scout")

    assert merge_problem(realm.state, DATA, "ada", [six, four]) is None
    assert merge_problem(realm.state, DATA, "ada", [six, four, one]) == (
        "Together they have 11 units, and an army holds at most 10."
    )
    assert merge_problem(realm.state, DATA, "ada", [one, away]) == (
        "Armies merge on one tile: a3 at (3, 2), a4 at (4, 2). Move them together first."
    )
    for too_few in [[], [six], [six, six], [six, four, six]]:
        assert merge_problem(realm.state, DATA, "ada", too_few) == (
            "Name at least two different armies to merge."
        )


def test_disbanded_army_is_gone_and_costs_no_upkeep(realm):
    army = realm.army("ada", CENTER, "spearman", "horseman")
    realm.round()
    assert realm.of_type("production")[-1]["upkeep"] == {"food": 3}

    disband(realm.state, realm.ctx, "ada", army)
    realm.round()

    assert realm.state.armies == []
    assert realm.of_type("production")[-1]["upkeep"] == {}


# --- founding cities ----------------------------------------------------------


def test_settler_founds_a_city_where_its_army_stands_and_is_used_up(realm):
    spot = (5, 2)
    army = realm.army("ada", spot, "spearman", "settler", "settler")

    city = settle(realm.state, DATA, realm.ctx, "ada", army)

    assert city == "c2"
    assert (realm.state.city(city).owner, realm.state.city(city).tile) == ("ada", spot)
    assert realm.units(army) == ["spearman", "settler"]
    assert realm.of_type("units_lost") == [{"army": army, "indexes": [1], "reason": "settled"}]


def test_army_of_a_lone_settler_is_gone_after_founding(realm):
    army = realm.army("ada", (5, 2), "settler")

    settle(realm.state, DATA, realm.ctx, "ada", army)

    assert realm.state.armies == []
    assert realm.army("ada", CENTER, "scout") == "a2"  # a1 is not used again


@pytest.mark.parametrize(("spot", "allowed"), [((4, 2), False), ((3, 2), False), ((5, 2), True)])
def test_new_city_must_be_two_steps_from_any_other(realm, spot, allowed):
    army = realm.army("ada", spot, "settler")

    problem = settle_problem(realm.state, DATA, "ada", army)

    assert (problem is None) == allowed
    if not allowed:
        col, row = spot
        assert problem == (
            "A new city must be at least 2 steps from every other city, and "
            f"a1 at ({col}, {row}) is closer to one. Move it first."
        )


def test_army_without_a_settler_cannot_found_a_city(realm):
    army = realm.army("ada", (5, 2), "spearman", "scout")

    assert settle_problem(realm.state, DATA, "ada", army) == (
        "a1 has no unit that founds a city (settler)."
    )


# --- hunger -------------------------------------------------------------------


def hungry_realm(seed: int = 0) -> Realm:
    """Ada's city makes 2 food more than it eats; her six units need 6 and her stock is empty."""
    realm = Realm(bare_map(), seed=seed)
    realm.found("ada", CENTER)
    realm.stock()["food"] = 0
    realm.army("ada", CENTER, "spearman", "spearman", "spearman")
    realm.army("ada", (0, 0), "archer", "archer", "archer")
    return realm


def test_hungry_nation_loses_a_random_unit_each_round_until_it_can_feed_the_rest():
    realm = hungry_realm()

    sizes = []
    for _ in range(6):
        realm.round()
        sizes.append(len(realm.state.units_of("ada")))

    assert sizes == [5, 4, 3, 2, 2, 2]
    lost = realm.of_type("units_lost")
    assert len(lost) == 4
    assert all(event["reason"] == "starved" and len(event["indexes"]) == 1 for event in lost)
    assert realm.state.nations["ada"].hungry_rounds == 0


def test_which_unit_starves_depends_on_the_seed_alone():
    def first_loss(seed: int) -> tuple:
        realm = hungry_realm(seed)
        realm.round()
        (event,) = realm.of_type("units_lost")
        return event["army"], event["indexes"][0]

    picks = [first_loss(seed) for seed in range(12)]

    assert picks == [first_loss(seed) for seed in range(12)]
    assert {army for army, _ in picks} == {"a1", "a2"}
    assert {index for _, index in picks} == {0, 1, 2}


def test_army_that_loses_its_last_unit_is_gone():
    realm = Realm(bare_map())
    realm.stock("bo")["food"] = 0
    realm.army("bo", (0, 0), "spearman")

    realm.round()

    assert realm.state.armies == []
    assert realm.of_type("units_lost") == [{"army": "a1", "indexes": [0], "reason": "starved"}]
    realm.round()  # nothing left to lose
    assert len(realm.of_type("units_lost")) == 1


def test_how_many_units_starve_in_a_round_comes_from_the_data():
    data = with_balance("army", starving_units_lost_per_round=2)
    realm = Realm(bare_map(), data=data)
    realm.stock("ada")["food"] = 0
    realm.stock("bo")["food"] = 0
    realm.army("ada", CENTER, "spearman", "spearman")
    realm.army("ada", (0, 0), "archer")
    realm.army("bo", (0, 0), "spearman")

    realm.round()

    assert len(realm.state.units_of("ada")) == 1
    assert sum(len(event["indexes"]) for event in realm.of_type("units_lost")) == 3
    assert realm.state.units_of("bo") == []  # it had one unit to lose, not two


def test_granary_puts_the_losses_off_by_two_rounds():
    realm = hungry_realm()
    realm.state.city("c1").buildings.append("granary")

    sizes = []
    for _ in range(4):
        realm.round()
        sizes.append(len(realm.state.units_of("ada")))

    assert sizes == [6, 6, 5, 4]


# --- sight --------------------------------------------------------------------


def test_army_sees_two_tiles_and_a_scout_in_it_two_more(realm):
    realm.army("ada", (0, 0), "spearman", "settler")
    realm.army("bo", (6, 4), "spearman")
    realm.army("ada", CENTER, "spearman", "scout")

    assert army_viewpoints(realm.state, DATA, "ada") == [((0, 0), 2), (CENTER, 4)]
    assert army_viewpoints(realm.state, DATA, "bo") == [((6, 4), 2)]


# --- orders that are not legal -------------------------------------------------


def test_illegal_order_raises_and_changes_nothing(realm):
    army = realm.army("ada", CENTER, "spearman")
    other = realm.army("ada", (0, 0), "spearman")
    before = realm.state.model_copy(deep=True)
    events = len(realm.events)

    with pytest.raises(ValueError, match="is trained in a barracks"):
        train(realm.state, DATA, realm.ctx, "ada", "c1", "archer", 1)
    with pytest.raises(ValueError, match="cannot reach"):
        move(realm.state, DATA, realm.ctx, "ada", army, (6, 4))
    with pytest.raises(ValueError, match="must leave a unit behind"):
        split(realm.state, realm.ctx, "ada", army, ["spearman"])
    with pytest.raises(ValueError, match="merge on one tile"):
        merge(realm.state, DATA, realm.ctx, "ada", [army, other])
    with pytest.raises(ValueError, match="You have no army"):
        disband(realm.state, realm.ctx, "bo", army)
    with pytest.raises(ValueError, match="no unit that founds a city"):
        settle(realm.state, DATA, realm.ctx, "ada", other)

    assert realm.state == before
    assert len(realm.events) == events
