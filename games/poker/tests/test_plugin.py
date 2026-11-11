import asyncio
import random

import pytest

from arena.agents.random_bot import RandomBot, random_bots
from arena.engine.match import Match
from arena.engine.plugin import TurnContext
from arena.engine.replay import replay
from arena.engine.rng import derive_rng
from arena.engine.types import MESSAGE, Action, Event, Reply, TurnRequest
from games.poker.cards import FULL_DECK
from games.poker.plugin import Poker

SEATS = ["p1", "p2", "p3", "p4", "p5", "p6"]


# --- helpers -------------------------------------------------------------------


class StackedDeck:
    """A stand-in random stream whose shuffle puts the given cards on top."""

    def __init__(self, top):
        self.top = top

    def shuffle(self, cards):
        rest = [c for c in cards if str(c) not in self.top]
        by_text = {str(c): c for c in cards}
        cards[:] = [by_text[t] for t in self.top] + rest


class Table:
    """One hand with chosen stacks and cards. `holes` in seat order, then the five board cards."""

    def __init__(self, stacks, holes, board, *, small_blind=10, settings=None):
        self.plugin = Poker()
        players = list(stacks)
        self.state = self.plugin.initial_state(
            players, {"small_blind": small_blind, **(settings or {})}
        )
        self.state.stacks = dict(stacks)
        self.total = sum(stacks.values())
        self.events: list[Event] = []
        top = [card for hole in holes for card in hole.split()] + board.split()
        self.deck = StackedDeck(top)
        self.plugin.setup(self.state, self.ctx())

    def ctx(self):
        def stream(*key):
            return self.deck if key[0] == "deck" else random.Random(str(key))

        def record(event):
            self.plugin.apply_event(self.state, event)
            self.events.append(event)

        return TurnContext(stream, record)

    def act(self, player, tool, **arguments):
        assert self.plugin.active_players(self.state) == [player], self.plugin.active_players(
            self.state
        )
        action = Action(tool=tool, arguments=arguments)
        problem = self.plugin.validate(self.state, player, action)
        assert problem is None, problem
        self.plugin.apply_actions(self.state, {player: action}, self.ctx())

    def tools_of(self, player):
        return {t.name for t in self.plugin.get_tools(self.state, player)}

    def problem(self, player, tool, **arguments):
        return self.plugin.validate(self.state, player, Action(tool=tool, arguments=arguments))

    def of_type(self, type):
        return [e.data for e in self.events if e.type == type]

    def after_first_hand(self):
        """Stacks when hand 1 ended (before the next hand's blinds)."""
        return dict(self.state.started_with) if self.state.hand_no > 1 else dict(self.state.stacks)

    def chips(self):
        return sum(self.state.stacks.values()) + sum(self.state.contributions.values())


def bot_match(players, *, seed=1, settings=None, agents=None, plugin=None):
    plugin = plugin or Poker()
    bots = random_bots(plugin, players, seed) | (agents or {})
    match = Match(plugin, bots, seed=seed, settings=settings or {})
    placements = asyncio.run(match.run())
    return match, placements


# --- settings ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("settings", "message"),
    [
        ({"ante": 5}, "Unknown settings"),
        ({"hand_limit": 0}, "hand_limit must be a whole number of at least 1"),
        ({"starting_stack": 15}, "at least one big blind"),
        ({"duplicate": {"deck_seed": 1}}, "exactly {deck_seed, rotation}"),
    ],
)
def test_bad_settings_are_rejected(settings, message):
    with pytest.raises(ValueError, match=message):
        Poker().initial_state(SEATS[:3], settings)


# --- positions and blinds ----------------------------------------------------------


def test_three_handed_blinds_and_action_order():
    table = Table({"a": 1000, "b": 1000, "c": 1000}, ["2c 3d", "4c 5d", "6c 7d"], "Kh Qs 9d 8c 2h")

    started = table.of_type("hand_started")[0]
    assert (started["button"], started["small_blind_player"], started["big_blind_player"]) == (
        "a",
        "b",
        "c",
    )
    assert [(b["player"], b["amount"]) for b in table.of_type("blind_posted")] == [
        ("b", 10),
        ("c", 20),
    ]
    assert table.plugin.active_players(table.state) == ["a"]  # left of the big blind
    table.act("a", "call")
    table.act("b", "call")
    table.act("c", "check")
    assert table.state.street_name == "flop"
    assert table.plugin.active_players(table.state) == ["b"]  # first left of the button


def test_heads_up_button_posts_small_blind_and_acts_first_preflop_last_after():
    table = Table({"a": 1000, "b": 1000}, ["2c 3d", "4c 5d"], "Kh Qs 9d 8c 2h")

    started = table.of_type("hand_started")[0]
    assert (started["button"], started["small_blind_player"], started["big_blind_player"]) == (
        "a",
        "a",
        "b",
    )
    assert table.plugin.active_players(table.state) == ["a"]
    table.act("a", "call")
    table.act("b", "check")
    assert table.plugin.active_players(table.state) == ["b"]


class Passive:
    """Checks when it can, otherwise calls: hands go to showdown without busting anyone."""

    async def act(self, request: TurnRequest) -> Reply:
        names = {tool.name for tool in request.tools}
        return Reply(action=Action(tool="check" if "check" in names else "call"))


def test_blinds_double_every_ten_hands():
    passive = {p: Passive() for p in SEATS[:2]}
    settings = {"starting_stack": 100000, "hand_limit": 12}
    match, _ = bot_match(SEATS[:2], seed=2, settings=settings, agents=passive)

    blinds = {
        h["hand"]: (h["small_blind"], h["big_blind"])
        for h in (e.data for e in match.events if e.type == "hand_started")
    }
    assert blinds[1] == blinds[10] == (10, 20)
    assert blinds[11] == (20, 40)


def test_button_moves_and_skips_eliminated_players():
    match, _ = bot_match(SEATS[:4], seed=3)
    hands = [e.data for e in match.events if e.type == "hand_started"]

    for previous, current in zip(hands, hands[1:], strict=False):
        seated = current["players"]
        order = SEATS[:4]
        start = order.index(previous["button"])
        expected = next(
            order[(start + i) % 4] for i in range(1, 5) if order[(start + i) % 4] in seated
        )
        assert current["button"] == expected


def test_a_short_blind_posts_what_it_has():
    table = Table({"a": 1000, "b": 1000, "c": 15}, ["2c 3d", "4c 5d", "6c 7d"], "Kh Qs 9d 8c 2h")

    assert table.of_type("blind_posted")[1] == {"player": "c", "amount": 15, "kind": "big"}
    assert table.state.street.all_in == ["c"]


# --- betting through the plugin ---------------------------------------------------


def test_min_raise_and_mistakes_are_explained():
    table = Table({"a": 1000, "b": 1000, "c": 1000}, ["2c 3d", "4c 5d", "6c 7d"], "Kh Qs 9d 8c 2h")

    assert table.problem("a", "raise", amount=30) == (
        "The minimum raise is to 40 (the bet of 20 plus the last raise of 20)."
    )
    assert table.problem("a", "check") == "You cannot check: 20 to call. Call, raise or fold."
    tools = {t.name: t for t in table.plugin.get_tools(table.state, "a")}
    assert set(tools) == {"fold", "call", "raise", "all_in", "table_talk"}
    assert tools["raise"].parameters["properties"]["amount"] == {
        "type": "integer",
        "minimum": 40,
        "maximum": 1000,
    }


def test_no_all_in_tool_when_it_would_be_a_raise_after_a_short_all_in():
    table = Table({"a": 1000, "b": 1000, "c": 130}, ["2c 3d", "4c 5d", "6c 7d"], "Kh Qs 9d 8c 2h")
    table.act("a", "raise", amount=100)
    table.act("b", "call")
    table.act("c", "all_in")  # 130: a raise of only 30 over 100

    assert set(table.tools_of("a")) == {"fold", "call", "table_talk"}
    assert table.problem("a", "all_in") == (
        "You may not raise now, and all your chips would be a raise; call or fold."
    )


def test_all_in_tool_stays_when_it_is_only_a_call():
    table = Table({"a": 1000, "b": 1000, "c": 50}, ["2c 3d", "4c 5d", "6c 7d"], "Kh Qs 9d 8c 2h")
    table.act("a", "raise", amount=100)
    table.act("b", "call")

    # c: big blind 20 + 30 behind = 50, less than the 100 to call.
    assert "all_in" in table.tools_of("c")


def test_table_talk_once_per_turn_within_40_words():
    table = Table({"a": 1000, "b": 1000}, ["2c 3d", "4c 5d"], "Kh Qs 9d 8c 2h")

    assert table.problem("a", "table_talk", text=" ".join(["w"] * 41)) == (
        "Your text has 41 words; say it in at most 40."
    )
    table.act("a", "table_talk", text="I never bluff.")
    assert table.plugin.active_players(table.state) == ["a"]
    assert {"player": "a", "text": "I never bluff."} in table.of_type(MESSAGE)
    assert table.problem("a", "table_talk", text="again") == (
        "You already talked this turn; now fold, check, call, raise or go all in."
    )


def test_everyone_folds_to_the_big_blind_without_a_showdown():
    table = Table({"a": 1000, "b": 1000, "c": 1000}, ["2c 3d", "4c 5d", "6c 7d"], "Kh Qs 9d 8c 2h")
    table.act("a", "fold")
    table.act("b", "fold")

    assert table.of_type("showdown") == []
    assert table.of_type("pot_awarded")[0] == {"amount": 30, "eligible": ["c"], "shares": {"c": 30}}
    assert table.after_first_hand() == {"a": 1000, "b": 990, "c": 1010}


# --- showdown, side pots, odd chips ---------------------------------------------


def test_showdown_reveals_live_hands_and_pays_the_best():
    holes = ["As Ad", "Kc Kd", "7h 2s"]
    table = Table({"a": 1000, "b": 1000, "c": 1000}, holes, "Ah 9c 5d 3s Qh")
    table.act("a", "call")
    table.act("b", "call")
    table.act("c", "check")
    for _ in range(3):  # check down flop, turn and river
        for player in ("b", "c", "a"):
            table.act(player, "check")

    shown = table.of_type("showdown")[0]["hands"]
    assert [(h["player"], h["cards"], h["hand"]) for h in shown] == [
        ("a", ["As", "Ad"], "three_of_a_kind"),
        ("b", ["Kc", "Kd"], "one_pair"),
        ("c", ["7h", "2s"], "high_card"),
    ]
    assert table.of_type("pot_awarded") == [
        {"amount": 60, "eligible": ["a", "b", "c"], "shares": {"a": 60}}
    ]


@pytest.mark.parametrize(
    ("stacks", "holes", "board", "expected"),
    [
        (  # two all-ins: the short stack wins the main pot, the big stack its side pot back
            {"a": 1000, "b": 100, "c": 300},
            ["7h 2s", "As Ad", "Kc Kd"],
            "Ah 9c 5d 3s Qh",
            {"a": 700, "b": 300, "c": 400},
        ),
        (  # three all-ins with unequal stacks, the biggest hand has the smallest stack
            {"a": 1000, "b": 50, "c": 200, "d": 500},
            ["7h 2s", "As Ad", "Kc Kd", "Qd Qc"],
            "Ah 9c 5d 3s 8h",
            {"a": 500, "b": 200, "c": 450, "d": 600},
        ),
    ],
)
def test_side_pots_with_several_all_ins(stacks, holes, board, expected):
    table = Table(stacks, holes, board)
    total = table.chips()
    first = table.plugin.active_players(table.state)[0]
    table.act(first, "all_in")
    while table.state.hand_no == 1 and table.plugin.active_players(table.state):
        player = table.plugin.active_players(table.state)[0]
        tools = {t.name for t in table.plugin.get_tools(table.state, player)}
        table.act(player, "call" if "call" in tools else "check")

    final = {p: chips for p, chips in table.after_first_hand().items() if chips} | {
        p: 0 for p in stacks if p not in table.after_first_hand()
    }
    assert {p: final.get(p, table.state.stacks[p]) for p in stacks} == expected
    assert sum(expected.values()) == total


def test_four_all_ins_pay_each_pot_to_its_best_eligible_hand():
    stacks = {"a": 30, "b": 80, "c": 150, "d": 300, "e": 300}
    holes = ["As Ad", "Ks Kd", "Qs Qd", "Js Jd", "7h 2c"]
    table = Table(stacks, holes, "Ah Kh Qh 3c 4d", small_blind=5)
    for player in ("d", "e", "a", "b", "c"):
        if table.plugin.active_players(table.state) == [player]:
            table.act(player, "all_in")
    assert table.state.hand_no == 2  # everyone was all-in: the board ran out, hand 1 is over
    first_hand = table.events[
        : next(i for i, e in enumerate(table.events) if e.type == "hand_ended")
    ]
    pots = [e.data for e in first_hand if e.type == "pot_awarded"]
    assert [p["amount"] for p in pots] == [150, 200, 210, 300]
    assert [p["shares"] for p in pots] == [{"a": 150}, {"b": 200}, {"c": 210}, {"d": 300}]


def test_odd_chip_goes_to_the_first_winner_left_of_the_button():
    # Board plays (a royal flush), so both live players tie. Pot 5 + 10 + 10 = 25.
    table = Table(
        {"a": 1000, "b": 1000, "c": 1000},
        ["2c 3d", "4c 5d", "6c 7d"],
        "As Ks Qs Js Ts",
        small_blind=5,
    )
    table.act("a", "call")
    table.act("b", "fold")
    table.act("c", "check")
    for _ in range(3):
        for player in ("c", "a"):
            table.act(player, "check")

    assert table.of_type("pot_awarded") == [
        {"amount": 25, "eligible": ["a", "c"], "shares": {"c": 13, "a": 12}}
    ]


def test_uncalled_bet_is_returned():
    table = Table({"a": 1000, "b": 200}, ["As Ad", "7h 2s"], "Ah 9c 5d 3s Qh")
    table.act("a", "raise", amount=600)
    table.act("b", "call")  # b is all-in for 200

    pots = table.of_type("pot_awarded")
    assert pots[0] == {"amount": 400, "eligible": ["a", "b"], "shares": {"a": 400}}
    assert pots[1] == {"amount": 400, "eligible": ["a"], "shares": {"a": 400}}


# --- elimination and the end -------------------------------------------------------


def test_tournament_plays_to_a_single_winner():
    match, placements = bot_match(SEATS[:4], seed=8)

    assert [e.data["reason"] for e in match.events if e.type == "match_over"] == ["last_player"]
    assert [p.rank for p in placements].count(1) == 1
    assert sum(match.state.stacks.values()) == 4000


def test_hand_limit_ranks_by_stack():
    match, placements = bot_match(
        SEATS[:3], seed=4, settings={"hand_limit": 3, "starting_stack": 5000}
    )

    assert match.state.hand_no == 3
    assert [e.data["reason"] for e in match.events if e.type == "match_over"] == ["hand_limit"]
    by_rank = sorted(placements, key=lambda p: p.rank)
    stacks = [match.state.stacks[p.player] for p in by_rank]
    assert stacks == sorted(stacks, reverse=True)


def test_results_rank_eliminations_and_share_ties():
    plugin = Poker()
    state = plugin.initial_state(SEATS[:5], {})
    state.stacks = {"p1": 3000, "p2": 0, "p3": 0, "p4": 0, "p5": 2000}
    state.eliminated = [[("p2", 500)], [("p3", 900), ("p4", 900)]]

    ranks = {(p.player, p.rank) for p in plugin.results(state)}

    assert ranks == {("p1", 1), ("p5", 2), ("p3", 3), ("p4", 3), ("p2", 5)}


# --- invariants over many hands ----------------------------------------------------


class Checked(Poker):
    """Poker that checks after every hand that no chip appeared or vanished."""

    hands = 0

    def apply_event(self, state, event):
        super().apply_event(state, event)
        if event.type == "hand_ended":
            Checked.hands += 1
            assert sum(state.stacks.values()) == state.starting_stack * len(state.players)
            assert all(stack >= 0 for stack in state.stacks.values())


def test_chips_are_conserved_over_1000_random_bot_hands():
    Checked.hands = 0
    rng = random.Random(0)
    seed = 0
    while Checked.hands < 1000:
        seed += 1
        players = SEATS[: rng.randint(2, 6)]
        bot_match(players, seed=seed, plugin=Checked(), settings={"hand_limit": 60})

    assert Checked.hands >= 1000


# --- hidden information ---------------------------------------------------------


class Spy:
    def __init__(self, plugin, rng):
        self.bot = RandomBot(plugin, rng)
        self.requests: list[TurnRequest] = []

    async def act(self, request):
        self.requests.append(request)
        return await self.bot.act(request)


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_no_player_sees_another_players_hole_cards_or_the_deck(seed):
    plugin = Poker()
    spies = {p: Spy(plugin, derive_rng(seed, "spy", p)) for p in SEATS[:4]}
    asyncio.run(Match(plugin, spies, seed=seed, settings={"hand_limit": 20}).run())

    for player, spy in spies.items():
        assert spy.requests
        for request in spy.requests:
            shown = set()
            own = set()
            for event in request.events:
                assert event.type != "deck_shuffled"
                if event.type == "hole_dealt":
                    assert event.data["player"] == player
                    own = set(event.data["cards"])
                if event.type == "showdown":
                    shown |= {c for h in event.data["hands"] for c in h["cards"]}
            observed = set(request.observation["your_cards"])
            assert observed == own or not observed
            board = set(request.observation["board"])
            text = repr(request.observation)
            others = {str(c) for c in FULL_DECK} - own - board - shown
            assert not any(f"'{card}'" in text for card in others), player


def test_observation_is_a_copy():
    table = Table({"a": 1000, "b": 1000}, ["2c 3d", "4c 5d"], "Kh Qs 9d 8c 2h")
    seen = table.plugin.get_observation(table.state, "a")

    seen["your_cards"].append("Ah")
    seen["players"][0]["stack"] = 0

    assert table.state.hole["a"] == ["2c", "3d"] and table.state.stacks["a"] == 990


# --- determinism, replay, duplicate ------------------------------------------------


def test_same_seed_same_match():
    first, a = bot_match(SEATS[:3], seed=11)
    second, b = bot_match(SEATS[:3], seed=11)
    other, _ = bot_match(SEATS[:3], seed=12)

    assert first.events == second.events and a == b
    assert first.events != other.events


def test_replay_rebuilds_the_end_state():
    match, _ = bot_match(SEATS[:4], seed=13)

    assert replay(Poker(), match.events) == match.state


def test_duplicate_mode_deals_the_same_cards_to_the_same_seat():
    def settings(rotation):
        return {
            "duplicate": {"deck_seed": 77, "rotation": rotation},
            "hand_limit": 1,
        }

    first, _ = bot_match(SEATS[:3], seed=1, settings=settings(0))
    second, _ = bot_match(SEATS[:3], seed=99, settings=settings(1))

    def by_seat(match):
        seats = match.state.seats
        holes = {e.data["player"]: e.data["cards"] for e in match.events if e.type == "hole_dealt"}
        return seats, [holes[p] for p in seats]

    seats_a, cards_a = by_seat(first)
    seats_b, cards_b = by_seat(second)
    assert cards_a == cards_b  # seat 1 gets the same cards in both matches...
    assert seats_a != seats_b  # ...but a different player sits there
    assert seats_b == SEATS[1:3] + SEATS[:1]

    def deck(match):
        return next(e.data["cards"] for e in match.events if e.type == "deck_shuffled")

    assert deck(first) == deck(second)


def test_200_random_bot_matches_finish():
    rng = random.Random(5)
    for number in range(200):
        players = SEATS[: rng.randint(2, 6)]
        match, placements = bot_match(players, seed=number, settings={"hand_limit": 30})
        assert match.state.phase == "over"
        assert sorted(p.player for p in placements) == sorted(players)


def test_opponent_stats_count_hands_and_raises():
    match, _ = bot_match(SEATS[:3], seed=21, settings={"hand_limit": 15, "starting_stack": 20000})
    raises = {
        p: sum(
            1
            for e in match.events
            if e.type == "bet_action" and e.data["player"] == p and e.data["kind"] == "raise"
        )
        for p in SEATS[:3]
    }

    seen = Poker().get_observation(match.state, "p1")["opponents"]
    assert set(seen) == {"p2", "p3"}
    assert seen["p2"]["raises"] == raises["p2"]
    dealt = [e.data["players"] for e in match.events if e.type == "hand_started"]
    assert seen["p2"]["hands"] == sum("p2" in players for players in dealt)


def test_render_spec_shows_every_hole_card_to_spectators():
    table = Table({"a": 1000, "b": 1000}, ["2c 3d", "4c 5d"], "Kh Qs 9d 8c 2h")

    spec = table.plugin.render_spec(table.state)

    assert spec["layout"] == "poker_table"
    assert [s["cards"] for s in spec["seats"]] == [["2c", "3d"], ["4c", "5d"]]
