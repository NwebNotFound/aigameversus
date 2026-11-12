"""Random events: each effect, who learns of it, the streams, and the log rebuilding the state."""

import json

from arena.engine.types import Event
from games.civ import events
from games.civ.state import NEUTRAL, CivState, new_game
from games.civ.tests.realm import CENTER, DATA, RING, Realm, bare_map, flat_map, reordered
from games.civ.turn import apply_event


def only(event_id: str, chance: float = 1.0, **changes):
    """The shipped data with one event that always strikes and none of the others."""
    picked = {
        key: event.model_copy(
            update={
                "probability_per_round": chance if key == event_id else 0.0,
                **(changes if key == event_id else {}),
            }
        )
        for key, event in DATA.events.items()
    }
    return DATA.model_copy(update={"events": picked})


def realm(data, world=None, players=("ada", "bo")):
    world_ = Realm(world or flat_map("plains"), players, data)
    world_.start_round()
    return world_


def last(world):
    return world.events[-1]


def test_plague_takes_one_population_but_never_empties_a_city():
    world = realm(only("plague"))
    city = world.found("ada", CENTER, population=3)

    events.roll(world.state, world.data, world.ctx)

    assert world.state.city(city).population == 2
    assert (last(world).type, last(world).visible_to) == ("random_event", ("ada",))
    small = realm(only("plague"))
    town = small.found("bo", CENTER, population=1)
    events.roll(small.state, small.data, small.ctx)
    assert last(small).data["population"] == 1
    assert small.state.city(town).population == 1


def test_gold_find_and_good_harvest_add_to_the_nations_stock():
    world = realm(only("gold_find"))
    before = {p: dict(world.stock(p)) for p in ("ada", "bo")}

    events.roll(world.state, world.data, world.ctx)

    (nation,) = last(world).visible_to
    assert world.stock(nation)["gold"] == before[nation]["gold"] + 25
    harvest = realm(only("good_harvest"))
    harvest.found("bo", CENTER)
    food = harvest.stock("bo")["food"]
    events.roll(harvest.state, harvest.data, harvest.ctx)
    assert harvest.stock("bo")["food"] == food + 5
    assert last(harvest).data["city"] == "c1"


def test_a_drought_halves_the_food_of_cities_in_its_region_for_its_rounds():
    world = realm(only("drought"), bare_map({tile: "plains" for tile in RING}))
    city = world.found("ada", CENTER)
    food = world.yields(city)["food"]

    events.roll(world.state, world.data, world.ctx)

    (condition,) = world.state.conditions
    assert (condition.col, condition.row, condition.radius) == (*CENTER, 2)
    assert condition.until_round == world.state.round + 3  # the next three productions
    assert world.yields(city)["food"] == food - food // 2
    for _ in range(4):  # its three rounds of production, then one without
        world.round()
    # Over: the yield is what it is without the drought (the city may have grown meanwhile).
    with_it = world.yields(city)
    kept, world.state.conditions = world.state.conditions, []
    assert with_it == world.yields(city)
    world.state.conditions = kept


def test_a_drought_cuts_exactly_its_rounds_of_production_in_the_shipped_order():
    # Rolled at the end of a round, after its production, like turn.py runs it.
    world = realm(only("drought"), bare_map({tile: "plains" for tile in RING}))
    city = world.found("ada", CENTER)
    world.end_round()
    events.roll(world.state, world.data, world.ctx)
    world.data = only("drought", chance=0.0)  # this one drought only

    cut = 0
    for _ in range(6):
        world.start_round()
        # What economy.produce books this round, with and without the drought.
        dry = world.yields(city)["food"]
        kept, world.state.conditions = world.state.conditions, []
        wet = world.yields(city)["food"]
        world.state.conditions = kept
        cut += dry < wet
        world.end_round()
        events.roll(world.state, world.data, world.ctx)

    assert cut == DATA.events["drought"].duration_rounds == 3


def test_a_drought_is_news_only_to_the_nations_with_a_city_in_its_region():
    world = realm(only("drought"), flat_map("plains"))
    world.found("ada", CENTER)
    world.found("bo", (6, 4))  # four steps away, outside the radius of 2

    events.roll(world.state, world.data, world.ctx)

    drought = last(world)
    assert drought.type == "random_event" and drought.data["event"] == "drought"
    centre = (drought.data["condition"]["col"], drought.data["condition"]["row"])
    hit = "ada" if centre == CENTER else "bo"
    assert drought.visible_to == (hit,)


def test_rebellion_only_takes_a_recently_conquered_city_and_makes_it_neutral():
    world = realm(only("rebellion"))
    old = world.found("ada", CENTER)
    events.roll(world.state, world.data, world.ctx)
    assert world.state.city(old).owner == "ada"  # never conquered: no rebellion

    world.state.city(old).conquered_round = world.state.round - 3
    world.round()
    events.roll(world.state, world.data, world.ctx)

    assert world.state.city(old).owner == NEUTRAL
    assert last(world).data["from"] == "ada" and last(world).visible_to == ("ada",)


def test_barbarians_appear_on_a_free_passable_tile_for_spectators_only():
    world = realm(only("barbarians"), flat_map("plains", {(0, 0): "mountains"}))
    world.found("ada", CENTER)

    events.roll(world.state, world.data, world.ctx)

    (army,) = world.state.armies
    assert army.owner == NEUTRAL and army.tile != CENTER
    assert DATA.terrain[world.state.world.terrain(army.tile)].movement_cost is not None
    assert sorted(t.kind for t in army.units) == ["spearman", "spearman", "swordsman"]
    assert last(world).visible_to == ()
    assert world.state.armies_raised == 1


def test_an_event_without_a_target_does_nothing():
    world = realm(only("plague"))  # no cities

    events.roll(world.state, world.data, world.ctx)

    assert not any(e.type == "random_event" for e in world.events)


def test_each_event_draws_from_its_own_stream_so_adding_one_changes_no_other():
    def struck(data, seed):
        world = Realm(flat_map("plains"), ("ada", "bo"), data, seed=seed)
        world.found("ada", CENTER, population=5)
        for _ in range(30):
            world.start_round()
            events.roll(world.state, world.data, world.ctx)
            world.end_round()
        return [
            (e.data["event"], e.data["round"]) for e in world.events if e.type == "random_event"
        ]

    everything = struck(DATA, 4)
    without_gold = struck(
        only("gold_find", chance=0.0)
        if False
        else DATA.model_copy(
            update={"events": {k: v for k, v in DATA.events.items() if k != "gold_find"}}
        ),
        4,
    )

    assert [e for e in everything if e[0] != "gold_find"] == [
        e for e in without_gold if e[0] != "gold_find"
    ]
    assert everything == struck(DATA, 4)  # the same seed, the same events


def test_the_log_rebuilds_the_state_with_events_of_every_kind():
    data = DATA.model_copy(
        update={
            "events": {
                k: v.model_copy(update={"probability_per_round": 1.0})
                for k, v in DATA.events.items()
            }
        }
    )
    world = Realm(flat_map("plains"), ("ada", "bo"), data, seed=2)
    world.found("ada", CENTER, population=4)
    world.state.city("c1").conquered_round = 0
    for _ in range(3):
        world.start_round()
        events.roll(world.state, world.data, world.ctx)
        world.end_round()

    rebuilt = CivState(world=world.state.world, nations=new_game(["ada", "bo"], data).nations)
    for event in world.events:
        stored = reordered(json.loads(json.dumps(event.data)))
        apply_event(rebuilt, Event(source=event.source, type=event.type, data=stored))
    # Realm.found sets population and conquest outside the log, as a test shortcut.
    rebuilt.city("c1").conquered_round = 0

    kinds = {e.data["event"] for e in world.events if e.type == "random_event"}
    assert kinds == set(DATA.events)
    assert rebuilt.model_dump(exclude={"cities"}) == world.state.model_dump(exclude={"cities"})
    assert [c.owner for c in rebuilt.cities] == [c.owner for c in world.state.cities]
