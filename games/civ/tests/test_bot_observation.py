"""The random bot plays 20 legal rounds from the observation; the observation shows only what the fog lets through."""  # noqa: E501

import json

import pytest

from arena.engine.rng import derive_rng
from games.civ import armies, economy
from games.civ.bot import random_orders
from games.civ.observation import FOG, visible_to
from games.civ.observation import observe as observe_with
from games.civ.plugin import scoreboard
from games.civ.tests.realm import DATA, Realm
from games.civ.turn import begin_round
from games.civ.world import generate_map

PLAYERS = ["ada", "bo", "cy", "di"]


def observe(state, data, player, **kw):
    return observe_with(state, data, player, scoreboard=scoreboard(state, data), **kw)


def new_realm(seed: int) -> Realm:
    world = generate_map(PLAYERS, DATA, derive_rng(seed, "map"))
    realm = Realm(world, players=PLAYERS, seed=seed)
    for start in world.starts:
        economy.found_city(realm.state, realm.ctx, start.player, start.tile)
    armies.deploy_start_units(realm.state, DATA, realm.ctx)
    return realm


def carry_out(realm: Realm, player: str, order: dict) -> None:
    """Run one order through the rules, as the turn flow will: it must be legal."""
    s, ctx, kind = realm.state, realm.ctx, order["type"]
    problem = {
        "build": lambda: economy.build_problem(s, DATA, player, order["city"], order["building"]),
        "train": lambda: armies.train_problem(
            s, DATA, player, order["city"], order["unit"], order["count"]
        ),
        "focus": lambda: economy.focus_problem(s, DATA, player, order["city"], order["focus"]),
        "move": lambda: armies.move_problem(s, DATA, player, order["army"], tuple(order["to"])),
        "split": lambda: armies.split_problem(s, player, order["army"], order["units"]),
        "disband": lambda: armies.disband_problem(s, player, order["army"]),
        "settle": lambda: armies.settle_problem(s, DATA, player, order["army"]),
        "merge": lambda: armies.merge_problem(s, DATA, player, order["armies"]),
        "respond": lambda: None,
    }[kind]()
    assert problem is None, (player, order, problem)
    if kind == "build":
        economy.build(s, DATA, ctx, player, order["city"], order["building"])
    elif kind == "train":
        armies.train(s, DATA, ctx, player, order["city"], order["unit"], order["count"])
    elif kind == "focus":
        economy.set_focus(s, DATA, ctx, player, order["city"], order["focus"])
    elif kind == "move":
        armies.move(s, DATA, ctx, player, order["army"], tuple(order["to"]))
    elif kind == "split":
        armies.split(s, ctx, player, order["army"], order["units"])
    elif kind == "disband":
        armies.disband(s, ctx, player, order["army"])
    elif kind == "settle":
        armies.settle(s, DATA, ctx, player, order["army"])
    elif kind == "merge":
        armies.merge(s, DATA, ctx, player, order["armies"])


def play_round(realm: Realm, rng) -> dict[str, list]:
    """One round as the turn flow runs it: every nation answers on the same state."""
    begin_round(realm.state, realm.ctx)
    economy.finish_construction(realm.state, realm.ctx)
    calls = {p: random_orders(observe(realm.state, DATA, p), rng) for p in PLAYERS}
    for player, call in calls.items():
        cities = [o for o in call["orders"] if o["type"] in ("build", "train", "focus")]
        rest = [o for o in call["orders"] if o not in cities]
        for order in cities + rest:
            carry_out(realm, player, order)
    economy.produce(realm.state, DATA, realm.ctx)
    armies.starve(realm.state, DATA, realm.ctx)
    economy.grow(realm.state, DATA, realm.ctx)
    return calls


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_the_bot_plays_twenty_rounds_without_one_illegal_order(seed):
    realm = new_realm(seed)
    rng = derive_rng(seed, "bot")
    total = 0
    for _ in range(20):
        calls = play_round(realm, rng)
        total += sum(len(call["orders"]) for call in calls.values())
        json.dumps(calls)  # plain data all the way

    assert total > 20
    assert len(realm.state.cities) >= len(PLAYERS)


def test_the_same_seed_gives_the_same_orders():
    first, second = new_realm(4), new_realm(4)

    a = [play_round(first, derive_rng(4, "bot", i)) for i in range(5)]
    b = [play_round(second, derive_rng(4, "bot", i)) for i in range(5)]

    assert a == b


def test_a_nation_without_cities_or_armies_gets_an_empty_call():
    realm = new_realm(5)
    realm.state.cities = [c for c in realm.state.cities if c.owner != "ada"]
    realm.state.armies = [a for a in realm.state.armies if a.owner != "ada"]

    observation = observe(realm.state, DATA, "ada")

    assert random_orders(observation, derive_rng(5, "bot")) == {"orders": []}


def test_the_bot_never_attacks_and_answers_offers():
    realm = new_realm(6)
    rng = derive_rng(6, "bot")
    for _ in range(5):
        play_round(realm, rng)
    observation = observe(realm.state, DATA, "ada") | {"offers": [{"id": "o4"}]}

    call = random_orders(observation, derive_rng(1, "x"))

    occupied = {tuple(c["tile"]) for c in observation["seen"]["cities"]}
    occupied |= {tuple(a["tile"]) for a in observation["seen"]["armies"]}
    assert all(tuple(o["to"]) not in occupied for o in call["orders"] if o["type"] == "move")
    assert {"type": "respond", "offer": "o4", "accept": True} in call["orders"] or {
        "type": "respond",
        "offer": "o4",
        "accept": False,
    } in call["orders"]


def test_the_observation_is_small_plain_json_and_fog_limited():
    realm = new_realm(6)
    rng = derive_rng(6, "bot")
    for _ in range(5):
        play_round(realm, rng)

    for player in PLAYERS:
        observation = observe(realm.state, DATA, player)
        seen = visible_to(realm.state, DATA, player)
        rows = observation["map"]["rows"]

        assert len(json.dumps(observation)) < 8000
        assert len(observation["cities"]) == sum(c.owner == player for c in realm.state.cities)
        assert len(rows) == len(realm.state.world.rows)
        assert all(len(row) == len(realm.state.world.rows[0]) for row in rows)
        assert sum(ch != FOG for row in rows for ch in row) == len(seen)
        for city in observation["seen"]["cities"]:
            assert city["owner"] != player and tuple(city["tile"]) in seen
        for army in observation["seen"]["armies"]:
            assert army["owner"] != player and tuple(army["tile"]) in seen
            assert isinstance(army["units"], int)  # a size, not the makeup


def test_the_observation_lists_only_what_can_be_done_now_and_how_close_each_win_is():
    realm = new_realm(9)
    begin_round(realm.state, realm.ctx)
    observation = observe(
        realm.state,
        DATA,
        "ada",
        extras={"gold_held_rounds": 2, "refused": ["move a9: no such army"]},
        plan="build a farm",
    )

    city = observation["cities"][0]
    legal = observation["legal"]["cities"][city["id"]]
    for building, cost in legal["build"].items():
        assert economy.build_problem(realm.state, DATA, "ada", city["id"], building) is None
        assert cost == dict(DATA.buildings[building].cost)
    for unit, most in legal["train"].items():
        assert armies.train_problem(realm.state, DATA, "ada", city["id"], unit, most) is None
        assert armies.train_problem(realm.state, DATA, "ada", city["id"], unit, most + 1)
        assert unit in observation["legal"]["unit_cost"]
    army = observation["armies"][0]
    for tile in army["reachable"]:
        assert armies.move_problem(realm.state, DATA, "ada", army["id"], tuple(tile)) is None
    victory = observation["victory"]
    assert victory["domination"].startswith("1 of 2 cities needed (4 exist)")
    assert "held 2 of 5" in victory["economy"]
    assert victory["closest_win"] in ("domination", "economy")
    assert observation["rounds_total"] == DATA.victory.round_limit.rounds
    assert observation["refused"] == ["move a9: no such army"]
    assert observation["your_plan_from_last_round"] == "build a farm"


def test_armies_on_one_tile_are_merged_as_far_as_they_fit_and_get_no_other_order():
    def army(army_id, units, tile=(1, 1)):
        return {"id": army_id, "tile": list(tile), "units": units, "reachable": [[2, 1]],
                "can_settle": False}  # fmt: skip

    observation = {
        "stock": {},
        "legal": {"cities": {}, "unit_cost": {}},
        "cities": [],
        "seen": {"cities": [], "armies": []},
        "offers": [],
        "armies": [
            army("a1", {"spearman": 4}),
            army("a2", {"archer": 5}),
            army("a3", {"swordsman": 2}),  # would make eleven
            army("a4", {"scout": 1}, tile=(5, 5)),
        ],
    }

    orders = random_orders(observation, derive_rng(1, "bot"))

    assert {"type": "merge", "armies": ["a1", "a2"]} in orders["orders"]
    assert not [o for o in orders["orders"] if o.get("army") in ("a1", "a2")]


def test_the_victory_lines_use_the_public_scoreboard_not_the_state():
    realm = new_realm(12)
    board = scoreboard(realm.state, DATA)
    lie = board | {
        "cities_total": 99,
        "domination_needed": 50,
        "cities": {**board["cities"], "ada": 7},
    }

    seen = observe_with(realm.state, DATA, "ada", scoreboard=lie)

    assert seen["victory"]["domination"] == "7 of 50 cities needed (99 exist)"


def test_the_observation_names_no_foreign_city_the_fog_hides_even_though_totals_are_public():
    realm = new_realm(13)
    board = scoreboard(realm.state, DATA)
    seen = observe(realm.state, DATA, "ada")
    visible = {tuple(c["tile"]) for c in seen["seen"]["cities"]}
    everywhere = {c.tile for c in realm.state.cities if c.owner != "ada"}

    assert board["cities_total"] == len(realm.state.cities)  # the count is public
    assert visible <= everywhere and len(visible) < len(everywhere)  # where they are is not
