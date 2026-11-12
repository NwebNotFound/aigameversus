"""The playable game (step 7.6): the round, submit_orders, barbarians, the scoreboard, the board."""

import asyncio
import json

import pytest

from arena.agents import estimate as estimating
from arena.agents.mock_llm import MockLLM, tool_call
from arena.agents.model import ModelError
from arena.agents.random_bot import random_bots
from arena.agents.runner import ModelAgent
from arena.config import load_config
from arena.engine.match import Match
from arena.engine.plugin import TurnContext
from arena.engine.replay import replay
from arena.engine.rng import derive_rng
from arena.engine.types import Action, Reply
from games.civ import combat, diplomacy, neutrals, orders
from games.civ.plugin import CivGame, scoreboard
from games.civ.state import NEUTRAL
from games.civ.tests.realm import CENTER, DATA, RICH, Realm, flat_map, reordered
from games.civ.world import Start, WorldMap

PLUGIN = CivGame()
FOUR = ["p1", "p2", "p3", "p4"]
SIX = ["p1", "p2", "p3", "p4", "p5", "p6"]
EAST = (4, 2)  # next to CENTER
OBSERVATION_BYTES = 17_500  # 5,000 tokens at 3.5 bytes each (docs/civ-interfaces.md)


def bot_match(players=FOUR, seed=1, agents=None) -> Match:
    seats = random_bots(PLUGIN, players, seed) | (agents or {})
    match = Match(PLUGIN, seats, seed=seed)
    asyncio.run(match.run())
    return match


def of_type(events, kind):
    return [e for e in events if e.type == kind]


class Watcher:
    """A random bot that keeps every observation it is given."""

    def __init__(self, bot):
        self.bot, self.seen = bot, []

    async def act(self, request):
        self.seen.append(request.observation)
        return await self.bot.act(request)


class Orders:
    """A nation that sends the same call every round."""

    def __init__(self, arguments):
        self.arguments, self.requests = arguments, []

    async def act(self, request):
        self.requests.append(request)
        return Reply(action=Action(tool="submit_orders", arguments=self.arguments))


# --- a whole match ----------------------------------------------------------------


@pytest.mark.parametrize("players", [FOUR, FOUR + ["p5"], SIX], ids=["4", "5", "6"])
def test_a_bot_match_ends_in_a_victory_and_its_log_rebuilds_it_whatever_the_key_order(players):
    match = bot_match(players, seed=2)

    won = of_type(match.events, "victory")
    assert len(won) == 1 and match.events[-1].type == "match_finished"
    assert {p["player"] for p in match.events[-1].data["placements"]} == set(players)
    assert of_type(match.events, "round_started")[-1].data["round"] == match.state.round
    stored = [e.model_copy(update={"data": reordered(e.data)}) for e in match.events]
    assert replay(PLUGIN, stored) == match.state


def test_the_same_seed_gives_the_same_match_and_another_seed_another():
    first, again, other = bot_match(seed=4), bot_match(seed=4), bot_match(seed=5)

    assert first.events == again.events
    assert other.events != first.events


def test_setup_draws_a_map_for_spectators_founds_every_capital_and_opens_round_one():
    state = PLUGIN.initial_state(FOUR, {})
    events = []

    def record(event):
        events.append(event)
        PLUGIN.apply_event(state, event)

    PLUGIN.setup(state, TurnContext(lambda *key: derive_rng(1, *key), record))

    drawn = of_type(events, "map_drawn")[0]
    assert drawn.visible_to == ()
    capitals = {(c.owner, c.tile) for c in state.cities}
    assert capitals == {(s.player, s.tile) for s in state.world.starts}
    assert state.round == 1 and PLUGIN.active_players(state) == FOUR


@pytest.mark.parametrize(
    ("players", "settings", "words"),
    [
        (FOUR[:3], {}, "4 to 6"),
        (FOUR, {"rounds": 5}, "Unknown settings"),
        (["neutral", *FOUR[:3]], {}, "barbarians"),
    ],
)
def test_bad_seats_and_settings_are_refused(players, settings, words):
    with pytest.raises(ValueError, match=words):
        PLUGIN.initial_state(players, settings)


def test_every_observation_of_a_six_nation_bot_match_stays_within_the_size_budget():
    watchers = {p: Watcher(bot) for p, bot in random_bots(PLUGIN, SIX, 3).items()}
    match = Match(PLUGIN, watchers, seed=3)
    asyncio.run(match.run())

    sizes = [len(json.dumps(seen)) for w in watchers.values() for seen in w.seen]
    assert len(sizes) > DATA.victory.round_limit.rounds  # every nation, while it lives
    assert max(sizes) <= OBSERVATION_BYTES


# --- what a nation sees -------------------------------------------------------------


def wide() -> WorldMap:
    """Twelve tiles wide: two cities at its ends do not see each other."""
    return WorldMap(rows=[["plains"] * 12 for _ in range(5)], starts=[])


def started(players=FOUR) -> Realm:
    """Two nations side by side on a plain, each with its capital, round 1 open."""
    realm = Realm(flat_map("plains"), players=players)
    realm.state.world.starts = [
        Start(player="p1", col=CENTER[0], row=CENTER[1], scarce="iron"),
        Start(player="p2", col=EAST[0] + 2, row=EAST[1], scarce="iron"),
    ]
    realm.found("p1", CENTER)
    realm.found("p2", (EAST[0] + 2, EAST[1]))
    realm.start_round()
    return realm


def test_the_scoreboard_is_public_and_built_from_the_state_alone():
    realm = started()
    realm.state.rich_rounds = {"p2": 2}
    realm.state.nations["p2"].stock["gold"] = 512

    board = scoreboard(realm.state, DATA)

    assert board["round"] == 1
    assert board["cities_total"] == 2 and board["cities"] == {"p1": 1, "p2": 1, "p3": 0, "p4": 0}
    assert board["domination_needed"] == 1
    assert board["gold_countdown"] == {"nation": "p2", "rounds_held": 2, "rounds_needed": 5}
    assert board["reputation"]["p1"] == 50
    assert "512" not in json.dumps(board)  # neither the gold nor a score that holds it
    assert PLUGIN.get_observation(realm.state, "p3")["scoreboard"] == board


def test_what_happens_in_the_fog_changes_only_the_public_counts_of_an_observation():
    realm = Realm(wide(), players=FOUR)
    realm.found("p1", (1, 2))
    far = realm.found("p2", (11, 2))
    realm.start_round()
    before = PLUGIN.get_observation(realm.state, "p1")

    realm.state.city(far).buildings.append("barracks")  # unseen: nothing changes
    realm.army("p2", (10, 2), "swordsman")
    assert PLUGIN.get_observation(realm.state, "p1") == before

    realm.found("p3", (11, 4))  # a new city far away: only the counts move
    after = PLUGIN.get_observation(realm.state, "p1")
    changed = {key for key in before if before[key] != after[key]}
    assert changed <= {"scoreboard", "victory"}
    assert after["scoreboard"]["cities_total"] == 3
    assert after["seen"] == before["seen"] and after["map"] == before["map"]


def test_legal_orders_name_the_types_that_can_do_something_now():
    realm = started()
    realm.army("p1", CENTER, "settler")

    legal = PLUGIN.get_observation(realm.state, "p1")["legal"]["orders"]

    assert "move" in legal and "focus" in legal and "declare_war" in legal
    assert "respond" not in legal and "break_treaty" not in legal and "pillage" not in legal
    assert "p2" in legal["declare_war"]


# --- submit_orders ------------------------------------------------------------------


def test_a_bad_order_is_dropped_for_its_nation_only_and_the_others_still_run():
    realm = started()
    realm.state.nations["p1"].stock = dict(RICH)
    given = [
        {"type": "build", "city": "c9", "building": "farm"},  # not their city
        {"type": "build", "city": "c1", "building": "farm"},
        {"type": "train", "city": "c1"},  # no unit
    ]

    orders.run(realm.state, DATA, realm.ctx, {"p1": given})

    refused = of_type(realm.events, "order_refused")
    assert [r.data["order"] for r in refused] == [given[0], given[2]]
    assert all(r.visible_to == ("p1",) for r in refused)
    assert "You have no city 'c9'" in refused[0].data["reason"]
    assert "needs city, unit; it has no unit" in refused[1].data["reason"]
    assert of_type(realm.events, "building_started")[0].data["building"] == "farm"


def test_talk_and_offers_beyond_the_limits_are_dropped():
    realm = started()
    talk = [{"type": "message", "to": None, "text": f"hello {i}"} for i in range(4)]
    long = {"type": "message", "to": "p2", "text": "word " * 61}
    offers = [{"type": "propose_treaty", "to": "p2", "kind": "peace"} for _ in range(4)]

    orders.run(realm.state, DATA, realm.ctx, {"p1": [*talk, long, *offers]})

    reasons = [r.data["reason"] for r in of_type(realm.events, "order_refused")]
    assert sum("At most 3 messages" in r for r in reasons) == 2  # the fourth, and the long one
    assert sum("treaty and trade offers" in r for r in reasons) == 1
    assert [m.data["text"] for m in of_type(realm.events, "message")] == [
        "hello 0",
        "hello 1",
        "hello 2",
    ]


def test_a_long_message_within_the_count_is_refused_for_its_length():
    realm = started()

    orders.run(realm.state, DATA, realm.ctx, {"p1": [{"type": "message", "text": "w " * 61}]})

    assert "at most 60 words" in of_type(realm.events, "order_refused")[0].data["reason"]


def test_moving_onto_another_nation_is_refused_in_peace_and_an_attack_at_war():
    realm = started()
    mine = realm.army("p1", CENTER, "swordsman", "swordsman", "swordsman")
    realm.army("p2", EAST, "spearman")
    move = {"type": "move", "army": mine, "to": list(EAST)}

    orders.run(realm.state, DATA, realm.ctx, {"p1": [move]})
    assert "not at war with p2" in of_type(realm.events, "order_refused")[0].data["reason"]

    realm.start_round()
    # Diplomacy runs before armies, whatever the order in the list.
    orders.run(realm.state, DATA, realm.ctx, {"p1": [move, {"type": "declare_war", "on": "p2"}]})
    combat.resolve(realm.state, DATA, realm.ctx)
    assert of_type(realm.events, "attack_ordered")[0].data == {"army": mine, "target": list(EAST)}
    assert of_type(realm.events, "battle")[0].data["winner"] in ("p1", "p2")


def test_a_move_into_the_fog_onto_a_held_tile_stops_before_it_and_cannot_probe_for_free():
    def move_into_fog(enemy_there: bool) -> Realm:
        realm = Realm(wide(), players=FOUR)
        realm.start_round()
        rider = realm.army("p1", (4, 2), "horseman")
        if enemy_there:
            realm.army("p2", (7, 2), "spearman")
        assert (7, 2) not in combat.sight(realm.state, DATA, "p1")
        orders.run(
            realm.state, DATA, realm.ctx, {"p1": [{"type": "move", "army": rider, "to": [7, 2]}]}
        )
        return realm

    free, held = move_into_fog(False), move_into_fog(True)

    assert free.state.army("a1").tile == (7, 2) and not of_type(free.events, "order_refused")
    assert held.state.army("a1").tile == (6, 2)  # it spent its move walking up to it
    assert "stopped before it" in of_type(held.events, "order_refused")[0].data["reason"]
    assert not of_type(held.events, "attack_ordered")


def test_orders_of_one_type_run_in_seat_order_whoever_listed_them_first():
    realm = started()
    for nation in ("p1", "p2"):
        realm.state.nations[nation].stock = dict(RICH)
    realm.found("p2", (0, 0))

    orders.run(
        realm.state,
        DATA,
        realm.ctx,
        {
            "p2": [{"type": "train", "city": "c3", "unit": "spearman"}],
            "p1": [{"type": "train", "city": "c1", "unit": "spearman"}],
        },
    )

    assert [e.data["owner"] for e in of_type(realm.events, "army_raised")] == ["p1", "p2"]


def test_an_offer_is_answered_next_round_and_a_trade_answer_finds_its_kind():
    realm = started()
    realm.state.nations["p1"].stock = dict(RICH)
    realm.state.nations["p2"].stock = dict(RICH)
    trade = {"type": "propose_trade", "to": "p2", "gives": {"wood": 2}, "wants": {"gold": 1}}
    orders.run(realm.state, DATA, realm.ctx, {"p1": [trade]})
    realm.start_round()

    offer = PLUGIN.get_observation(realm.state, "p2")["offers"][0]
    orders.run(
        realm.state,
        DATA,
        realm.ctx,
        {"p2": [{"type": "respond", "offer": offer["id"], "accept": True}]},
    )

    assert offer["from"] == "p1" and offer["gives"] == {"wood": 2}
    assert of_type(realm.events, "trade_agreed")
    assert not of_type(realm.events, "order_refused")


def test_the_plan_comes_back_to_its_nation_only_and_is_cut_to_sixty_words():
    plan = "Hold the river. " + "more " * 80
    sender = Orders({"orders": [], "plan": plan})
    other = Orders({"orders": []})
    match = Match(PLUGIN, random_bots(PLUGIN, FOUR, 1) | {"p1": sender, "p2": other}, seed=1)
    asyncio.run(match.run())

    kept = sender.requests[1].observation["your_plan_from_last_round"]
    assert kept.startswith("Hold the river.") and len(kept.split()) == 60
    assert of_type(match.events, "plan_set")[0].visible_to == ("p1",)
    assert all(
        "Hold the river" not in json.dumps(r.model_dump(mode="json")) for r in other.requests
    )


def test_the_tool_schema_caps_the_list():
    assert orders.SUBMIT_ORDERS.parameters["properties"]["orders"]["maxItems"] == orders.MAX_ORDERS
    items = orders.SUBMIT_ORDERS.parameters["properties"]["orders"]["items"]
    assert items["properties"]["type"]["enum"] == list(orders.ORDER_TYPES)


# --- barbarians -----------------------------------------------------------------------


def test_a_barbarian_army_attacks_what_is_next_to_it_without_any_war():
    realm = started()
    city = realm.state.cities[0]
    barbarians = realm.army(NEUTRAL, EAST, *["swordsman"] * 5)

    neutrals.act(realm.state, DATA, realm.ctx)
    combat.resolve(realm.state, DATA, realm.ctx)

    assert of_type(realm.events, "attack_ordered")[0].data["army"] == barbarians
    assert realm.state.city(city.id).owner == NEUTRAL  # undefended: taken
    assert of_type(realm.events, "city_conquered")[0].data["to"] == NEUTRAL


def test_a_barbarian_army_with_nothing_in_reach_walks_towards_the_nearest_city():
    realm = Realm(wide(), players=FOUR)
    realm.found("p1", (1, 2))
    realm.start_round()
    barbarians = realm.army(NEUTRAL, (10, 2), "spearman")

    neutrals.act(realm.state, DATA, realm.ctx)

    assert realm.state.army(barbarians).tile == (9, 2)
    assert not of_type(realm.events, "attack_ordered")


# --- models (mock only) -----------------------------------------------------------------


def test_a_match_of_mock_models_plays_to_the_end_with_failed_calls_and_garbled_answers():
    script = [
        ModelError("RateLimitError"),
        tool_call("submit_orders", {"orders": [{"type": "fly"}]}),  # refused by the schema
        tool_call(
            "submit_orders", {"orders": [{"type": "focus", "city": "c1", "focus": "growth"}]}
        ),
        tool_call("submit_orders", {"orders": [], "plan": "Grow."}),
    ]
    mock = MockLLM(*script)

    async def no_pause(seconds):
        return None

    agent = ModelAgent(mock, PLUGIN, sleep=no_pause)
    match = bot_match(seed=6, agents={"p1": agent})

    assert match.events[-1].type == "match_finished"
    rejected = [e for e in of_type(match.events, "action_rejected") if e.data["player"] == "p1"]
    assert rejected and "fly" in rejected[0].data["error"]
    played = [e for e in of_type(match.events, "action_accepted") if e.data["player"] == "p1"]
    assert len(played) > 1  # the nation plays on after the failed call and the refused answer
    prompt = json.dumps(mock.calls[-1][0])
    assert "submit_orders" in json.dumps(mock.calls[-1][1]) and '\\"scoreboard\\"' in prompt
    assert replay(PLUGIN, match.events) == match.state


def test_a_cost_estimate_counts_one_call_per_nation_and_round():
    config = load_config()
    model = next(iter(config.models))
    seats = {"p1": model, "p2": None, "p3": None, "p4": None}

    estimate = asyncio.run(estimating.estimate(PLUGIN, seats, {}, config, {}))

    assert set(estimate) == {"p1"}
    assert estimate["p1"].calls <= DATA.victory.round_limit.rounds
    assert estimate["p1"].estimate_micro_eur > 0


# --- the board ------------------------------------------------------------------------------


SPOILER_FREE = {
    "layout", "round", "rounds_total", "cols", "rows", "terrain", "legend",
    "cities", "armies", "nations", "treaties", "wars", "fog", "battles",
}  # fmt: skip


def test_the_spectator_board_shows_everything_and_one_nations_board_only_what_it_sees():
    match = bot_match(seed=2)
    state = match.state

    full = PLUGIN.render_spec(state)
    assert full["layout"] == "hex_map" and set(full["fog"]) == set(FOUR)
    assert len(full["terrain"]) == full["rows"] and len(full["terrain"][0]) == full["cols"]
    assert set(full["legend"].values()) <= set(DATA.terrain)

    mine = PLUGIN.render_spec_for(state, "p1")
    assert set(mine) == SPOILER_FREE and set(mine["fog"]) == {"p1"}
    seen = {
        (c, r)
        for r, line in enumerate(full["fog"]["p1"])
        for c, bit in enumerate(line)
        if bit == "1"
    }
    assert all(tuple(a["tile"]) in seen for a in mine["armies"])
    assert all("units" not in a for a in mine["armies"] if a["owner"] != "p1")
    assert all("stock" not in n for n in mine["nations"] if n["id"] != "p1")
    assert len(mine["cities"]) <= len(full["cities"])


def test_a_battle_marks_the_board_for_the_round_after_it():
    realm = started()
    diplomacy.declare_war(realm.state, DATA, realm.ctx, "p1", "p2")
    mine = realm.army("p1", CENTER, *["swordsman"] * 4)
    realm.army("p2", EAST, "spearman")
    combat.attack(realm.state, DATA, realm.ctx, "p1", mine, EAST)
    combat.resolve(realm.state, DATA, realm.ctx)
    realm.start_round()

    battles = PLUGIN.render_spec(realm.state)["battles"]

    assert battles == [{"round": 1, "tile": list(EAST), "winner": "p1", "nations": ["p1", "p2"]}]
    assert PLUGIN.render_spec_for(realm.state, "p3")["battles"] == []
