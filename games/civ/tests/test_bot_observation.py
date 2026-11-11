"""The random bot plays 20 legal rounds; the observation shows only what the fog lets through."""

import json

import pytest

from arena.engine.rng import derive_rng
from games.civ import armies, economy
from games.civ.bot import random_orders
from games.civ.observation import FOG, observe, visible_to
from games.civ.orders import apply_order, order_problem, sorted_for_the_round
from games.civ.tests.realm import DATA, Realm
from games.civ.turn import begin_round
from games.civ.world import generate_map

PLAYERS = ["ada", "bo", "cy", "di"]


def new_realm(seed: int) -> Realm:
    world = generate_map(PLAYERS, DATA, derive_rng(seed, "map"))
    realm = Realm(world, players=PLAYERS, seed=seed)
    for start in world.starts:
        economy.found_city(realm.state, realm.ctx, start.player, start.tile)
    armies.deploy_start_units(realm.state, DATA, realm.ctx)
    return realm


def play_round(realm: Realm, rng) -> dict[str, list]:
    """One round as the turn flow runs it, with bot orders; returns the orders by nation."""
    begin_round(realm.state, realm.ctx)
    economy.finish_construction(realm.state, realm.ctx)
    given = {}
    for player in PLAYERS:
        orders = random_orders(realm.state, DATA, player, rng)
        # the bot saw the state before anyone moved; apply them to the real one in phase order
        for order in sorted_for_the_round(orders):
            assert order_problem(realm.state, DATA, player, order) is None, (player, order)
            apply_order(realm.state, DATA, realm.ctx, player, order)
        given[player] = orders
    economy.produce(realm.state, DATA, realm.ctx)
    armies.starve(realm.state, DATA, realm.ctx)
    economy.grow(realm.state, DATA, realm.ctx)
    return given


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_the_bot_plays_twenty_rounds_without_one_illegal_order(seed):
    realm = new_realm(seed)
    rng = derive_rng(seed, "bot")
    total = 0
    for _ in range(20):
        total += sum(len(orders) for orders in play_round(realm, rng).values())
        json.dumps([e.data for e in realm.events])  # plain data all the way

    assert total > 20
    assert len(realm.state.cities) >= len(PLAYERS)


def test_the_same_seed_gives_the_same_orders():
    first = new_realm(4)
    second = new_realm(4)

    a = [play_round(first, derive_rng(4, "bot", i)) for i in range(5)]
    b = [play_round(second, derive_rng(4, "bot", i)) for i in range(5)]

    assert a == b


def test_a_player_without_cities_or_armies_gets_no_orders():
    realm = new_realm(5)
    realm.state.cities = [c for c in realm.state.cities if c.owner != "ada"]
    realm.state.armies = [a for a in realm.state.armies if a.owner != "ada"]

    assert random_orders(realm.state, DATA, "ada", derive_rng(5, "bot")) == []


def test_the_observation_is_small_plain_json_and_fog_limited():
    realm = new_realm(6)
    rng = derive_rng(6, "bot")
    for _ in range(5):
        play_round(realm, rng)

    for player in PLAYERS:
        observation = observe(realm.state, DATA, player)
        text = json.dumps(observation)
        seen = visible_to(realm.state, DATA, player)
        rows = observation["map"]["rows"]

        assert len(text) < 6000
        assert observation["overview"]["cities"] == sum(
            c.owner == player for c in realm.state.cities
        )
        assert len(rows) == len(realm.state.world.rows)
        assert all(len(row) == len(realm.state.world.rows[0]) for row in rows)
        assert sum(ch != FOG for row in rows for ch in row) == len(seen)
        for city in observation["seen"]["cities"]:
            assert city["owner"] != player and tuple(city["tile"]) in seen
        for army in observation["seen"]["armies"]:
            assert army["owner"] != player and tuple(army["tile"]) in seen
            assert isinstance(army["units"], int)  # a size, not the makeup


def test_an_enemy_far_away_is_not_in_the_observation():
    realm = new_realm(7)
    observation = observe(realm.state, DATA, "ada")
    start = {s.player: s.tile for s in realm.state.world.starts}
    near = {tuple(c["tile"]) for c in observation["seen"]["cities"]}

    for player in PLAYERS[1:]:
        assert (start[player] in near) == (start[player] in visible_to(realm.state, DATA, "ada"))


@pytest.mark.parametrize(
    ("order", "message"),
    [
        ({"order": "dance"}, "There is no order"),
        ({"order": "move", "army": "a1"}, "Missing: to"),
        ({"order": "move", "army": "a1", "to": "north"}, "to must be a tile"),
        ({"order": "train", "city": "c1", "unit": "spearman", "count": True}, "whole number"),
        ({"order": "merge", "armies": "a1"}, "list of army ids"),
    ],
)
def test_a_badly_formed_order_gets_a_message_not_an_error(order, message):
    realm = new_realm(8)
    owner = realm.state.cities[0].owner

    assert message in order_problem(realm.state, DATA, owner, order)
