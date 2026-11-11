"""The economy: what cities yield, building and demolishing, upkeep, hunger and growth."""

import random

import pytest

from games.civ.economy import (
    build,
    build_problem,
    building_slots,
    city_viewpoints,
    demolish,
    demolish_problem,
    focus_problem,
    set_focus,
    units_lost_to_hunger,
    upkeep,
)
from games.civ.fog import visible_tiles
from games.civ.state import new_game
from games.civ.tests.realm import (
    CENTER,
    DATA,
    PLAYERS,
    RICH,
    RING,
    Realm,
    bare_map,
    flat_map,
    with_building_rules,
)
from games.civ.world import distance, generate_map


@pytest.fixture
def realm() -> Realm:
    """Ada's city c1 on a map where only the city itself yields anything."""
    realm = Realm(bare_map())
    realm.found("ada", CENTER)
    return realm


# --- the start ----------------------------------------------------------------


def test_every_nation_starts_with_the_stock_from_the_data():
    state = new_game(["ada", "bo"], DATA)

    assert state.nations["ada"].stock == {"food": 5, "wood": 5, "iron": 0, "gold": 5}
    assert state.nations["bo"] == state.nations["ada"]
    state.nations["ada"].stock["gold"] = 0
    assert state.nations["bo"].stock["gold"] == 5
    assert state.cities == []


def test_new_city_has_one_population_and_no_buildings():
    realm = Realm(flat_map("plains"))

    assert realm.found("ada", CENTER) == "c1"
    assert realm.found("bo", (0, 0)) == "c2"

    city = realm.state.city("c2")
    assert (city.owner, city.tile, city.population, city.food) == ("bo", (0, 0), 1, 0)
    assert (city.focus, city.buildings, city.sites) == ("growth", [], [])


# --- yields -------------------------------------------------------------------


def test_city_yields_its_own_share_its_tiles_and_one_per_population():
    kinds = ["forest", "hills", "river", "iron_deposit", "water", "plains"]
    realm = Realm(bare_map(dict(zip(RING, kinds, strict=True))))
    realm.found("ada", CENTER)

    # city 2 food, 1 wood, 1 gold; forest 2 wood; hills 1 iron, 1 food; river 1 food, 1 gold;
    # iron deposit 3 iron; plains 2 food; one population on growth 1 food
    assert realm.yields("c1") == {"food": 7, "wood": 3, "iron": 4, "gold": 2}
    assert sorted(realm.worked("c1")) == sorted(RING)


def test_tile_under_the_city_yields_nothing():
    realm = Realm(bare_map({CENTER: "gold_vein"}))
    realm.found("ada", CENTER)

    assert realm.yields("c1") == {"food": 3, "wood": 1, "iron": 0, "gold": 1}


def test_city_works_the_second_ring_from_population_5():
    far = (5, 2)
    assert distance(CENTER, far) == 2
    realm = Realm(bare_map({far: "gold_vein"}))
    realm.found("ada", CENTER, population=4)
    assert realm.yields("c1")["gold"] == 1

    realm.state.city("c1").population = 5

    assert realm.yields("c1")["gold"] == 4
    assert len(realm.worked("c1")) == 18


@pytest.mark.parametrize("count", [4, 5, 6])
@pytest.mark.parametrize("seed", range(10))
def test_every_capital_starts_with_the_same_total_yield(count, seed):
    realm = Realm(generate_map(PLAYERS[:count], DATA, random.Random(seed)), PLAYERS[:count])
    capitals = [realm.found(start.player, start.tile) for start in realm.state.world.starts]

    assert {sum(realm.yields(capital).values()) for capital in capitals} == {17}


def test_population_adds_the_resource_of_the_city_focus(realm):
    realm.state.city("c1").population = 3
    assert realm.yields("c1") == {"food": 5, "wood": 1, "iron": 0, "gold": 1}

    set_focus(realm.state, DATA, realm.ctx, "ada", "c1", "production")
    assert realm.yields("c1") == {"food": 2, "wood": 4, "iron": 0, "gold": 1}

    set_focus(realm.state, DATA, realm.ctx, "ada", "c1", "military")
    assert realm.yields("c1") == {"food": 2, "wood": 1, "iron": 3, "gold": 1}


def test_focus_must_be_one_of_the_three_and_the_city_your_own(realm):
    assert focus_problem(realm.state, DATA, "ada", "c1", "growth") is None
    assert focus_problem(realm.state, DATA, "ada", "c1", "science") == (
        "There is no focus 'science'. Choose one of: growth, production, military."
    )
    assert focus_problem(realm.state, DATA, "bo", "c1", "growth") == (
        "You have no city 'c1'. Your cities: none."
    )


# --- tiles between cities -----------------------------------------------------


def test_tile_equally_near_to_two_cities_is_worked_by_the_older_one():
    shared = (3, 2)
    for first, second in [((2, 2), (4, 2)), ((4, 2), (2, 2))]:
        realm = Realm(flat_map("plains"))
        realm.found("ada", first)
        realm.found("bo", second)

        assert shared in realm.worked("c1")
        assert shared not in realm.worked("c2")
        assert (len(realm.worked("c1")), len(realm.worked("c2"))) == (6, 5)


def test_tile_is_worked_by_the_nearer_city_even_if_the_other_is_older_and_bigger():
    between = (3, 2)
    realm = Realm(flat_map("plains"))
    realm.found("ada", (1, 2), population=5)
    realm.found("bo", (4, 2))
    assert (distance((1, 2), between), distance((4, 2), between)) == (2, 1)

    assert between in realm.worked("c2")
    assert between not in realm.worked("c1")
    assert len(realm.worked("c2")) == 6


def test_older_city_does_not_hold_a_tile_beyond_its_own_radius():
    between = (3, 2)
    realm = Realm(flat_map("plains"))
    realm.found("ada", (1, 2))
    realm.found("bo", (5, 2), population=5)
    assert (distance((1, 2), between), distance((5, 2), between)) == (2, 2)

    assert between in realm.worked("c2")
    assert len(realm.worked("c1")) == 6


def test_nobody_works_a_tile_with_a_city_on_it():
    realm = Realm(flat_map("plains"))
    realm.found("ada", CENTER)
    realm.found("bo", (4, 2))

    assert sorted(realm.worked("c1")) == [(2, 1), (2, 2), (2, 3), (3, 1), (3, 3)]
    assert sorted(realm.worked("c2")) == [(4, 1), (4, 3), (5, 2)]


# --- building -----------------------------------------------------------------


def test_building_is_paid_at_once_and_works_from_the_next_round(realm):
    realm.start_round()
    realm.build("ada", "c1", "farm")

    assert realm.stock()["wood"] == 1
    city = realm.state.city("c1")
    assert (city.buildings, [site.building for site in city.sites]) == ([], ["farm"])
    assert realm.of_type("building_started") == [
        {"city": "c1", "building": "farm", "cost": {"wood": 4}, "rounds": 1}
    ]

    realm.end_round()
    assert realm.of_type("production")[-1]["yields"]["food"] == 3  # no farm yet

    realm.round()
    assert (city.buildings, city.sites) == (["farm"], [])
    assert realm.of_type("building_completed") == [{"city": "c1", "building": "farm"}]
    assert realm.of_type("production")[-1]["yields"]["food"] == 5
    assert realm.of_type("construction_progressed") == []


def test_building_takes_as_many_rounds_as_the_data_says():
    realm = Realm(bare_map(), data=with_building_rules(build_rounds=3))
    realm.found("ada", CENTER)
    realm.state.nations["ada"].stock = dict(RICH)
    city = realm.state.city("c1")

    realm.build("ada", "c1", "farm")
    realm.round()
    realm.build("ada", "c1", "sawmill")
    assert [(site.building, site.rounds_left) for site in city.sites] == [
        ("farm", 2),
        ("sawmill", 3),
    ]

    realm.round()
    assert (city.buildings, len(city.sites)) == ([], 2)
    realm.round()
    assert (city.buildings, [site.building for site in city.sites]) == (["farm"], ["sawmill"])
    realm.round()
    assert (city.buildings, city.sites) == (["farm", "sawmill"], [])
    assert len(realm.of_type("construction_progressed")) == 3


def test_of_two_sites_of_one_kind_the_older_is_finished_first():
    two_farms = DATA.buildings["farm"].model_copy(update={"max_per_city": 2})
    data = with_building_rules(build_rounds=2).model_copy(
        update={"buildings": {**DATA.buildings, "farm": two_farms}}
    )
    realm = Realm(bare_map(), data=data)
    realm.found("ada", CENTER)
    realm.state.nations["ada"].stock = dict(RICH)
    city = realm.state.city("c1")

    realm.build("ada", "c1", "farm")
    realm.round()
    realm.build("ada", "c1", "farm")
    realm.round()

    assert city.buildings == ["farm"]
    assert [(site.building, site.rounds_left) for site in city.sites] == [("farm", 1)]
    realm.round()
    assert (city.buildings, city.sites) == (["farm", "farm"], [])


@pytest.mark.parametrize(
    ("population", "slots"), [(1, 3), (2, 4), (3, 4), (4, 5), (9, 7), (10, 8), (11, 8), (40, 8)]
)
def test_city_has_3_slots_plus_one_per_2_population_up_to_8(population, slots):
    assert building_slots(DATA, population) == slots


def test_city_cannot_build_more_than_its_slots_and_sites_count(realm):
    realm.state.nations["ada"].stock = dict(RICH)
    realm.build("ada", "c1", "farm")
    realm.round()
    realm.build("ada", "c1", "sawmill")
    realm.build("ada", "c1", "market")

    assert build_problem(realm.state, DATA, "ada", "c1", "granary") == (
        "c1 has no free building slot: 3 of 3 are taken at population 1. "
        "Demolish a building or let the city grow."
    )

    realm.state.city("c1").population = 2
    assert build_problem(realm.state, DATA, "ada", "c1", "granary") is None


def test_city_cannot_have_a_building_twice_also_not_as_a_site(realm):
    realm.state.nations["ada"].stock = dict(RICH)
    realm.build("ada", "c1", "farm")
    twice = "c1 already has a farm, built or under construction (at most 1 per city)."

    assert build_problem(realm.state, DATA, "ada", "c1", "farm") == twice
    realm.round()
    assert realm.state.city("c1").buildings == ["farm"]
    assert build_problem(realm.state, DATA, "ada", "c1", "farm") == twice


@pytest.mark.parametrize(
    ("tiles", "allowed"),
    [
        ({}, False),
        ({RING[0]: "hills"}, True),
        ({RING[5]: "iron_deposit"}, True),
        ({(5, 2): "hills"}, False),  # two steps away
        ({CENTER: "hills"}, False),  # under the city, not next to it
    ],
)
def test_mine_needs_hills_or_iron_next_to_the_city(tiles, allowed):
    realm = Realm(bare_map(tiles))
    realm.found("ada", CENTER)

    problem = build_problem(realm.state, DATA, "ada", "c1", "mine")

    assert (problem is None) == allowed
    if not allowed:
        assert problem == "A mine needs hills or iron_deposit next to the city; c1 has none."


def test_building_that_cannot_be_paid_is_refused_with_cost_and_stock(realm):
    assert build_problem(realm.state, DATA, "ada", "c1", "market") is None
    realm.stock()["gold"] = 2

    assert build_problem(realm.state, DATA, "ada", "c1", "market") == (
        "A market costs 4 wood, 3 gold; you have 5 wood, 2 gold."
    )


def test_unknown_building_and_foreign_city_are_refused(realm):
    realm.found("bo", (0, 0))

    assert build_problem(realm.state, DATA, "ada", "c1", "castle") == (
        "There is no building 'castle'. Buildings: farm, sawmill, mine, market, barracks, "
        "wall, forge, granary, watchtower."
    )
    # A city of another nation is refused like one that does not exist.
    for city_id in ["c2", "c9"]:
        assert build_problem(realm.state, DATA, "ada", city_id, "farm") == (
            f"You have no city '{city_id}'. Your cities: c1."
        )


def test_illegal_order_raises_and_changes_nothing(realm):
    before = realm.state.model_copy(deep=True)

    with pytest.raises(ValueError, match="A wall costs 6 wood, 3 iron"):
        build(realm.state, DATA, realm.ctx, "ada", "c1", "wall")
    with pytest.raises(ValueError, match="c1 has no finished farm"):
        demolish(realm.state, DATA, realm.ctx, "ada", "c1", "farm")
    with pytest.raises(ValueError, match="There is no focus 'idle'"):
        set_focus(realm.state, DATA, realm.ctx, "ada", "c1", "idle")

    assert realm.state == before
    assert len(realm.events) == 1  # the founding of c1


# --- demolishing --------------------------------------------------------------


def test_demolishing_returns_half_the_cost_rounded_down_and_frees_the_slot():
    realm = Realm(bare_map())
    realm.found("ada", CENTER, "sawmill", "farm", "market")
    assert realm.yields("c1")["wood"] == 3
    assert build_problem(realm.state, DATA, "ada", "c1", "granary") is not None

    demolish(realm.state, DATA, realm.ctx, "ada", "c1", "sawmill")  # cost 3 wood, 1 gold

    assert realm.stock() == {"food": 5, "wood": 6, "iron": 0, "gold": 5}
    assert realm.state.city("c1").buildings == ["farm", "market"]
    assert realm.yields("c1")["wood"] == 1
    assert realm.of_type("building_demolished") == [
        {"city": "c1", "building": "sawmill", "refund": {"wood": 1, "gold": 0}}
    ]
    assert build_problem(realm.state, DATA, "ada", "c1", "granary") is None


def test_refund_is_the_exact_share_from_the_data_rounded_down():
    palace = DATA.buildings["wall"].model_copy(update={"cost": {"wood": 100, "iron": 3}})
    data = with_building_rules(demolish_refund=0.29).model_copy(
        update={"buildings": {**DATA.buildings, "wall": palace}}
    )
    realm = Realm(bare_map(), data=data)
    realm.found("ada", CENTER, "wall")

    demolish(realm.state, realm.data, realm.ctx, "ada", "c1", "wall")

    # 29 % of 100 is 29, also where binary fractions make it 28.999...
    assert realm.of_type("building_demolished")[0]["refund"] == {"wood": 29, "iron": 0}


def test_only_a_finished_building_of_your_own_city_can_be_demolished(realm):
    realm.build("ada", "c1", "farm")

    assert demolish_problem(realm.state, "ada", "c1", "farm") == (
        "c1 has no finished farm. Its buildings: none."
    )
    realm.round()
    assert demolish_problem(realm.state, "ada", "c1", "farm") is None
    assert demolish_problem(realm.state, "ada", "c1", "wall") == (
        "c1 has no finished wall. Its buildings: farm."
    )
    assert demolish_problem(realm.state, "bo", "c1", "farm") == (
        "You have no city 'c1'. Your cities: none."
    )


# --- production and upkeep ----------------------------------------------------


def test_production_adds_the_yields_to_the_stock_and_the_population_eats(realm):
    realm.round()

    assert realm.of_type("production") == [
        {
            "player": "ada",
            "yields": {"food": 3, "wood": 1, "iron": 0, "gold": 1},
            "eaten": 1,
            "upkeep": {},
            "stock": {"food": 7, "wood": 6, "iron": 0, "gold": 6},
            "hungry_rounds": 0,
            "stored": {"c1": 2},
        }
    ]
    assert realm.stock() == {"food": 7, "wood": 6, "iron": 0, "gold": 6}
    assert realm.stock("bo") == {"food": 5, "wood": 5, "iron": 0, "gold": 5}


def test_nation_takes_in_what_all_its_cities_yield():
    realm = Realm(flat_map("mountains"))
    realm.found("ada", (1, 1), "sawmill")
    realm.found("bo", (5, 3))
    realm.found("ada", (3, 3), population=2)

    realm.round()

    ada = realm.of_type("production")[0]
    assert ada["yields"] == {"food": 7, "wood": 4, "iron": 0, "gold": 2}
    assert ada["eaten"] == 3
    assert ada["stored"] == {"c1": 2, "c3": 2}
    assert realm.stock("ada") == {"food": 9, "wood": 9, "iron": 0, "gold": 7}
    assert realm.stock("bo") == {"food": 7, "wood": 6, "iron": 0, "gold": 6}


def test_units_cost_their_upkeep_every_round(realm):
    assert upkeep(DATA, []) == {}
    assert upkeep(DATA, ["scout"]) == {}
    assert upkeep(DATA, ["spearman", "settler"]) == {"food": 2}
    assert upkeep(DATA, ["horseman", "siege_engine", "siege_engine"]) == {"food": 4, "gold": 2}

    realm.round({"ada": ["spearman", "settler"], "bo": ["horseman"]})

    assert realm.of_type("production")[0]["upkeep"] == {"food": 2}
    assert realm.stock("ada")["food"] == 5  # 5 + 3 made - 1 eaten - 2 upkeep
    assert realm.stock("bo")["food"] == 3  # no city: 5 - 2 upkeep


def test_unpaid_upkeep_empties_the_stock_and_counts_the_hungry_rounds(realm):
    army = {"ada": ["spearman"] * 6}
    nation = realm.state.nations["ada"]

    realm.round(army)  # 5 + 3 - 1 = 7 food, 6 due
    assert (realm.stock()["food"], nation.hungry_rounds) == (1, 0)
    realm.round(army)  # 1 + 3 - 1 = 3 food, 6 due
    assert (realm.stock()["food"], nation.hungry_rounds) == (0, 1)
    realm.round(army)
    assert (realm.stock()["food"], nation.hungry_rounds) == (0, 2)

    realm.round({"ada": ["spearman"]})  # 0 + 3 - 1 = 2 food, 1 due
    assert (realm.stock()["food"], nation.hungry_rounds) == (1, 0)


def test_upkeep_in_gold_that_cannot_be_paid_counts_like_food(realm):
    realm.stock()["gold"] = 0

    realm.round({"ada": ["siege_engine"]})  # 1 gold made, 1 due: paid to the last coin
    assert (realm.stock()["gold"], realm.state.nations["ada"].hungry_rounds) == (0, 0)

    realm.round({"ada": ["siege_engine", "siege_engine"]})  # 1 gold made, 2 due
    assert realm.stock() == {"food": 6, "wood": 7, "iron": 0, "gold": 0}  # food 6 + 3 - 1 - 2
    assert realm.state.nations["ada"].hungry_rounds == 1


def test_first_unpaid_round_costs_a_unit(realm):
    army = {"ada": ["spearman"] * 9}
    assert units_lost_to_hunger(realm.state, DATA, "ada") == 0

    realm.round(army)

    assert units_lost_to_hunger(realm.state, DATA, "ada") == 1
    assert units_lost_to_hunger(realm.state, DATA, "bo") == 0


def test_granary_covers_two_hungry_rounds():
    realm = Realm(bare_map())
    realm.found("ada", CENTER, "granary")
    army = {"ada": ["spearman"] * 9}

    lost = []
    for _ in range(4):
        realm.round(army)
        lost.append(units_lost_to_hunger(realm.state, DATA, "ada"))

    assert lost == [0, 0, 1, 1]


def test_only_a_finished_granary_of_the_own_nation_counts_and_two_do_not_add_up():
    realm = Realm(flat_map("mountains"))
    realm.found("ada", (1, 1))
    realm.found("bo", (5, 3), "granary")
    realm.found("ada", (3, 3))
    realm.state.nations["ada"].hungry_rounds = 1
    assert units_lost_to_hunger(realm.state, DATA, "ada") == 1  # bo's granary is not ada's

    realm.build("ada", "c1", "granary")
    assert units_lost_to_hunger(realm.state, DATA, "ada") == 1

    realm.state.city("c1").buildings.append("granary")
    realm.state.city("c3").buildings.append("granary")
    assert units_lost_to_hunger(realm.state, DATA, "ada") == 0
    realm.state.nations["ada"].hungry_rounds = 3
    assert units_lost_to_hunger(realm.state, DATA, "ada") == 1
    realm.state.nations["ada"].hungry_rounds = 2
    assert units_lost_to_hunger(realm.state, DATA, "ada") == 0


def test_nation_without_cities_still_pays_for_its_units_and_one_with_nothing_is_left_out():
    realm = Realm(bare_map(), players=("ada", "bo", "cy"))
    realm.found("ada", CENTER)

    realm.round({"bo": ["spearman"] * 6})
    assert [event["player"] for event in realm.of_type("production")] == ["ada", "bo"]
    assert (realm.stock("bo")["food"], realm.state.nations["bo"].hungry_rounds) == (0, 1)
    assert len(realm.state.units_of("bo")) == 5  # and one of the six starved

    # Its units are gone: one more event clears the count, then none.
    realm.round({})
    realm.round()
    assert [event["player"] for event in realm.of_type("production")] == [
        "ada",
        "bo",
        "ada",
        "bo",
        "ada",
    ]
    assert realm.state.nations["bo"].hungry_rounds == 0


# --- growth -------------------------------------------------------------------


def test_city_gains_a_population_for_every_10_surplus_food_and_keeps_the_rest(realm):
    realm.state.city("c1").buildings.append("farm")  # 5 food made, 1 eaten: 4 surplus a round
    city = realm.state.city("c1")

    realm.round()
    realm.round()
    assert (city.population, city.food) == (1, 8)
    assert realm.of_type("city_grew") == []

    realm.round()
    assert (city.population, city.food) == (2, 2)
    assert realm.of_type("city_grew") == [{"city": "c1", "population": 2, "food": 2}]


def test_city_grows_in_the_round_its_surplus_reaches_10(realm):
    city = realm.state.city("c1")  # 3 food made, 1 eaten: 2 surplus a round

    for _ in range(4):
        realm.round()
    assert (city.population, city.food) == (1, 8)

    realm.round()
    assert (city.population, city.food) == (2, 0)


def test_city_grows_by_one_population_a_round_at_most(realm):
    city = realm.state.city("c1")
    city.food = 31

    realm.round()  # 2 surplus
    assert (city.population, city.food) == (2, 23)
    realm.round()
    assert (city.population, city.food) == (3, 15)


def test_city_that_eats_more_than_it_makes_takes_from_the_stock_and_collects_nothing(realm):
    city = realm.state.city("c1")
    city.population, city.food = 2, 6
    set_focus(realm.state, DATA, realm.ctx, "ada", "c1", "production")

    realm.round()  # 2 food made, 2 eaten
    assert realm.of_type("production")[0]["stored"] == {}
    assert (city.food, realm.stock()["food"]) == (6, 5)

    city.population = 4
    realm.round()  # 2 food made, 4 eaten
    assert realm.of_type("production")[1]["stored"] == {}
    assert (city.population, city.food) == (4, 6)
    assert realm.stock()["food"] == 3

    realm.round()
    realm.round()  # the stock is empty; nobody starves
    assert realm.stock()["food"] == 0
    assert (city.population, realm.state.nations["ada"].hungry_rounds) == (4, 0)


# --- sight --------------------------------------------------------------------


def test_city_sees_two_tiles_and_a_finished_watchtower_adds_two():
    realm = Realm(flat_map("plains"), players=("ada", "bo"))
    realm.found("ada", (0, 0))
    realm.found("bo", (6, 4))
    realm.found("ada", CENTER)
    realm.state.nations["ada"].stock = dict(RICH)
    assert city_viewpoints(realm.state, DATA, "ada") == [((0, 0), 2), (CENTER, 2)]

    realm.build("ada", "c3", "watchtower")
    assert city_viewpoints(realm.state, DATA, "ada") == [((0, 0), 2), (CENTER, 2)]
    realm.round()

    assert city_viewpoints(realm.state, DATA, "ada") == [((0, 0), 2), (CENTER, 4)]
    assert city_viewpoints(realm.state, DATA, "bo") == [((6, 4), 2)]
    seen = visible_tiles(realm.state.world, city_viewpoints(realm.state, DATA, "ada"))
    assert (6, 4) in seen
    assert len(seen) == 35
