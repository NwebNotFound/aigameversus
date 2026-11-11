"""Whole sessions: nations give random legal orders to their cities and armies, round by round."""

import json
import random
from itertools import combinations

import pytest

from arena.engine.types import Event
from games.civ.armies import (
    deploy_start_units,
    disband,
    merge,
    merge_problem,
    move,
    reachable,
    settle,
    settle_problem,
    split,
    train,
    train_problem,
)
from games.civ.data_loader import CivData
from games.civ.economy import (
    build_problem,
    building_slots,
    demolish,
    found_city,
    set_focus,
)
from games.civ.state import CivState, new_game
from games.civ.tests.realm import DATA, PLAYERS, Realm, reordered, with_building_rules
from games.civ.turn import apply_event
from games.civ.world import distance, generate_map

SLOW = with_building_rules(build_rounds=2)


def order_a_city(realm: Realm, player: str, rng: random.Random) -> None:
    state, data = realm.state, realm.data
    city_id = rng.choice([city.id for city in state.cities if city.owner == player])
    order = rng.choice(["build", "build", "train", "train", "demolish", "focus"])
    if order == "build":
        building = rng.choice(sorted(data.buildings))
        if build_problem(state, data, player, city_id, building) is None:
            realm.build(player, city_id, building)
    elif order == "train":
        unit, count = rng.choice(sorted(data.units)), rng.randint(1, 3)
        if train_problem(state, data, player, city_id, unit, count) is None:
            train(state, data, realm.ctx, player, city_id, unit, count)
    elif order == "demolish" and state.city(city_id).buildings:
        building = rng.choice(state.city(city_id).buildings)
        demolish(state, data, realm.ctx, player, city_id, building)
    elif order == "focus":
        set_focus(state, data, realm.ctx, player, city_id, rng.choice(["growth", "military"]))


def organise_an_army(realm: Realm, player: str, rng: random.Random) -> None:
    state, data = realm.state, realm.data
    own = [army for army in state.armies if army.owner == player]
    if not own:
        return
    army = rng.choice(own)
    order = rng.choice(["settle", "settle", "split", "merge", "merge", "disband"])
    if order == "settle" and settle_problem(state, data, player, army.id) is None:
        settle(state, data, realm.ctx, player, army.id)
    elif order == "split" and len(army.units) > 1:
        kinds = [troop.kind for troop in army.units]
        split(state, realm.ctx, player, army.id, rng.sample(kinds, rng.randrange(1, len(kinds))))
    elif order == "merge":
        here = [other.id for other in own if other.tile == army.tile]
        if merge_problem(state, data, player, here) is None:
            merge(state, data, realm.ctx, player, here)
    elif order == "disband" and rng.random() < 0.2:
        disband(state, realm.ctx, player, army.id)


def play(seed: int, count: int = 4, rounds: int = 40, data: CivData = DATA):
    """A session from the first round on. Yields the realm after each round."""
    rng = random.Random(seed)
    players = PLAYERS[:count]
    realm = Realm(generate_map(players, data, rng), players, data, seed)
    state = realm.state
    for start in state.world.starts:
        found_city(state, realm.ctx, start.player, start.tile)
    deploy_start_units(state, data, realm.ctx)

    for _ in range(rounds):
        realm.start_round()
        for player in players:
            for _ in range(rng.randrange(4)):
                order_a_city(realm, player, rng)
        for player in players:
            for _ in range(rng.randrange(3)):
                organise_an_army(realm, player, rng)
        for army in list(state.armies):  # every army moves once at most
            ways = sorted(reachable(state, data, army.id))
            if ways and rng.random() < 0.6:
                move(state, data, realm.ctx, army.owner, army.id, rng.choice(ways))
        realm.end_round()
        yield realm


def played(seed: int, **options) -> Realm:
    *_, realm = play(seed, **options)
    return realm


@pytest.mark.parametrize("count", [4, 5, 6])
@pytest.mark.parametrize("seed", range(5))
def test_random_orders_never_break_the_books(count, seed):
    for round_no, realm in enumerate(play(seed, count), start=1):
        state = realm.state
        assert state.round == round_no
        for nation in state.nations.values():
            assert all(amount >= 0 for amount in nation.stock.values())
            assert sorted(nation.stock) == ["food", "gold", "iron", "wood"]
            assert nation.hungry_rounds >= 0
        for city in state.cities:
            planned = city.buildings + [site.building for site in city.sites]
            assert len(planned) <= building_slots(DATA, city.population)
            assert all(planned.count(b) <= DATA.buildings[b].max_per_city for b in planned)
            assert city.population >= 1
            assert city.food >= 0
        for a, b in combinations(state.cities, 2):
            assert distance(a.tile, b.tile) >= DATA.balance.city.min_distance
        worked = {city.id: set(realm.worked(city.id)) for city in state.cities}
        for a, b in combinations(worked, 2):
            assert not worked[a] & worked[b]
        assert not set().union(*worked.values()) & {city.tile for city in state.cities}
        ids = [army.id for army in state.armies]
        assert len(set(ids)) == len(ids)
        assert all(int(army_id[1:]) <= state.armies_raised for army_id in ids)
        for army in state.armies:
            assert 1 <= len(army.units) <= DATA.balance.army.max_units
            assert DATA.terrain[state.world.terrain(army.tile)].movement_cost is not None


def test_sessions_use_every_kind_of_event_and_every_unit():
    realms = [played(seed, data=SLOW) for seed in range(5)]

    assert {event.type for realm in realms for event in realm.events} == {
        "round_started",
        "city_founded",
        "city_focus_set",
        "building_started",
        "building_completed",
        "construction_progressed",
        "building_demolished",
        "production",
        "city_grew",
        "army_raised",
        "army_moved",
        "army_split",
        "armies_merged",
        "army_disbanded",
        "units_lost",
    }
    reasons = {e["reason"] for realm in realms for e in realm.of_type("units_lost")}
    assert reasons == {"settled", "starved"}
    trained = {
        u["kind"] for realm in realms for e in realm.of_type("army_raised") for u in e["units"]
    }
    assert trained == set(DATA.units)
    assert any(len(realm.state.cities) > 4 for realm in realms)


@pytest.mark.parametrize("seed", range(5))
def test_same_seed_and_orders_give_the_same_events_and_state(seed):
    first, second = played(seed), played(seed)

    assert first.events == second.events
    assert first.state == second.state
    assert first.events != played(seed + 1).events


@pytest.mark.parametrize("data", [DATA, SLOW], ids=["shipped", "slow_building"])
@pytest.mark.parametrize("seed", range(5))
def test_log_rebuilds_the_state_whatever_the_order_of_keys(seed, data):
    realm = played(seed, count=5, data=data)
    rebuilt = CivState(world=realm.state.world, nations=new_game(PLAYERS[:5], data).nations)

    # Applying events needs no game data and no seed: the log alone carries what happened.
    for event in realm.events:
        stored = reordered(json.loads(json.dumps(event.data)))
        apply_event(rebuilt, Event(source=event.source, type=event.type, data=stored))

    assert rebuilt == realm.state


@pytest.mark.parametrize("data", [DATA, SLOW], ids=["shipped", "slow_building"])
@pytest.mark.parametrize("seed", range(5))
def test_every_event_but_the_round_count_is_private_to_its_nation(seed, data):
    realm = played(seed, data=data)
    owners: dict[str, str] = {}

    for event in realm.events:
        if event.type == "round_started":
            assert event.visible_to is None
            continue
        info = event.data
        if event.type in ("city_founded", "army_raised"):
            owners[info.get("city") or info["army"]] = info["owner"]
        if event.type == "army_split":
            owners[info["new_army"]] = owners[info["army"]]
        subject = info.get("city") or info.get("army") or info.get("into")
        assert event.visible_to == (info.get("player") or owners[subject],)
