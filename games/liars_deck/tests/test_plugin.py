import asyncio
import random
from collections import Counter

import pytest

from arena.agents.random_bot import RandomBot, random_bots
from arena.engine.match import Match
from arena.engine.plugin import TurnContext
from arena.engine.replay import replay
from arena.engine.rng import derive_rng
from arena.engine.types import MESSAGE, Action, Event, EventSource, Reply, TurnRequest
from games.liars_deck.plugin import DEVIL_ID, LiarsDeck, card_rank, deck_for
from games.liars_deck.variants import load_variants

SEATS = ["p1", "p2", "p3", "p4"]


# --- helpers -------------------------------------------------------------------


class Table:
    """A state built from hand-made events, for exact scenarios."""

    def __init__(self, hands, *, table_card="king", live=None, variant="base", starter=None):
        self.plugin = LiarsDeck()
        players = list(hands)
        self.state = self.plugin.initial_state(players, {"variant": variant})
        self.events: list[Event] = []
        self._draws = 0
        for player in players:
            self.apply("revolver_loaded", player=player, live=[(live or {}).get(player, 5)])
        self.apply(
            "round_started",
            round=1,
            table_card=table_card,
            starter=starter or players[0],
            hand_size=5,
            players=players,
        )
        for player, cards in hands.items():
            self.apply("hand_dealt", player=player, cards=cards)

    def apply(self, type, **data):
        self.plugin.apply_event(self.state, Event(source=EventSource.GAME, type=type, data=data))

    def ctx(self):
        def stream(*key):
            self._draws += 1
            return random.Random(f"{key}{self._draws}")

        def record(event):
            self.plugin.apply_event(self.state, event)
            self.events.append(event)

        return TurnContext(stream, record)

    def act(self, player, tool, **arguments):
        action = Action(tool=tool, arguments=arguments)
        problem = self.plugin.validate(self.state, player, action)
        assert problem is None, problem
        self.plugin.apply_actions(self.state, {player: action}, self.ctx())
        self.plugin.step(self.state, self.ctx())

    def problem(self, player, tool, **arguments):
        return self.plugin.validate(self.state, player, Action(tool=tool, arguments=arguments))

    def of_type(self, type):
        return [event.data for event in self.events if event.type == type]


def bot_match(players, *, seed=1, variant="base", agents=None):
    plugin = LiarsDeck()
    bots = random_bots(plugin, players, seed) | (agents or {})
    match = Match(plugin, bots, seed=seed, settings={"variant": variant})
    placements = asyncio.run(match.run())
    return match, placements


def game_events(match):
    return [event for event in match.events if event.source is EventSource.GAME]


# --- deck ----------------------------------------------------------------------


def test_base_deck_has_20_cards_by_rank():
    deck = deck_for(load_variants()["base"])

    assert len(deck) == len(set(deck)) == 20
    assert Counter(card_rank(card) for card in deck) == {
        "king": 6,
        "queen": 6,
        "ace": 6,
        "joker": 2,
    }


def test_devil_variant_makes_one_joker_the_devil_card():
    deck = deck_for(load_variants()["devil_card"])

    assert len(deck) == 20
    assert [card for card in deck if card_rank(card) == "joker"] == ["J1", DEVIL_ID]


# --- settings --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("players", "settings", "message"),
    [
        (SEATS, {"variant": "dice"}, "Unknown variant 'dice'"),
        (SEATS, {"jokers": 3}, "Unknown settings"),
        (["p1"], {}, "needs 2 to 4 players"),
    ],
)
def test_bad_settings_are_rejected(players, settings, message):
    with pytest.raises(ValueError, match=message):
        LiarsDeck().initial_state(players, settings)


# --- setup -----------------------------------------------------------------------


@pytest.mark.parametrize("count", [2, 3, 4])
def test_setup_deals_private_hands_and_hides_the_chambers(count):
    match, _ = bot_match(SEATS[:count])
    events = game_events(match)

    loaded = [e for e in events if e.type == "revolver_loaded"]
    assert [e.data["player"] for e in loaded] == SEATS[:count]
    assert all(e.visible_to == () for e in loaded)

    first_round = events[events.index(next(e for e in events if e.type == "round_started")) :][
        : count + 1
    ]
    assert first_round[0].visible_to is None
    deals = [e for e in first_round if e.type == "hand_dealt"]
    assert all(e.visible_to == (e.data["player"],) for e in deals)
    cards = [card for e in deals for card in e.data["cards"]]
    assert len(cards) == len(set(cards)) == 5 * count  # with fewer than 4 players, cards stay out


def test_revolver_risk_per_pull_is_one_in_remaining_chambers():
    """Over many seeds the chance to fall on pull k, having survived so far, is 1/(7 - k)."""
    plugin = LiarsDeck()
    fall_on = Counter()
    for seed in range(1200):
        state = plugin.initial_state(["p1", "p2"], {})
        context = TurnContext(
            lambda *key, seed=seed: derive_rng(seed, "game", *key),
            lambda event, state=state: plugin.apply_event(state, event),
        )
        plugin.setup(state, context)
        fall_on[state.live_chambers["p1"][0] + 1] += 1

    survivors = 1200
    for pull in range(1, 7):
        hazard = fall_on[pull] / survivors
        assert hazard == pytest.approx(1 / (7 - pull), abs=0.06 if pull < 6 else 0), pull
        survivors -= fall_on[pull]


def test_a_seat_falls_exactly_on_its_live_chamber():
    match, _ = bot_match(SEATS, seed=5)
    live = {
        e.data["player"]: e.data["live"][0] for e in match.events if e.type == "revolver_loaded"
    }

    for pull in (e.data for e in match.events if e.type == "trigger_pulled"):
        assert pull["live"] == (pull["pull"] - 1 == live[pull["player"]])


# --- reveal and shooter ------------------------------------------------------------


def test_caught_liar_pulls_the_trigger():
    table = Table({"p1": ["Q1", "K1"], "p2": ["K2", "K3"]}, table_card="king")
    table.act("p1", "play_cards", card_ids=["Q1"])

    table.act("p2", "call_liar")

    assert table.of_type("cards_revealed") == [
        {"player": "p1", "cards": ["Q1"], "honest": False, "devil": False}
    ]
    assert table.of_type("shooters_chosen") == [{"players": ["p1"], "reason": "caught_lying"}]
    assert table.state.pulls == {"p1": 1, "p2": 0}


def test_wrong_caller_pulls_the_trigger_and_jokers_count_as_table_card():
    table = Table({"p1": ["K1", "J1", "Q1"], "p2": ["A1"]}, table_card="king")
    table.act("p1", "play_cards", card_ids=["K1", "J1"])

    table.act("p2", "call_liar", text="No way.")

    assert table.of_type("cards_revealed")[0]["honest"] is True
    assert table.of_type("shooters_chosen") == [{"players": ["p2"], "reason": "wrong_call"}]
    assert {"player": "p2", "text": "No way."} in table.of_type(MESSAGE)


def test_only_the_last_play_is_revealed():
    table = Table({"p1": ["Q1", "K1"], "p2": ["A1", "K2"], "p3": ["K3"]}, table_card="king")
    table.act("p1", "play_cards", card_ids=["Q1"])  # a lie nobody calls
    table.act("p2", "play_cards", card_ids=["K2"])

    table.act("p3", "call_liar")

    assert table.of_type("cards_revealed") == [
        {"player": "p2", "cards": ["K2"], "honest": True, "devil": False}
    ]


def test_a_survivor_starts_the_new_round_with_new_cards():
    table = Table({"p1": ["Q1", "K1"], "p2": ["K2", "A2"]}, table_card="king", live={"p1": 5})
    table.act("p1", "play_cards", card_ids=["Q1"])

    table.act("p2", "call_liar")

    assert table.of_type("trigger_pulled") == [{"player": "p1", "pull": 1, "live": False}]
    started = table.of_type("round_started")
    assert started and started[0]["round"] == 2 and started[0]["starter"] == "p1"
    assert table.state.phase == "turn" and table.state.current == "p1"
    assert len(table.state.hands["p1"]) == len(table.state.hands["p2"]) == 5
    assert table.state.last_play is None and table.state.revealed_this_round == []


def test_a_live_chamber_eliminates_and_the_other_side_starts():
    hands = {"p1": ["Q1", "K1"], "p2": ["K2"], "p3": ["A3"]}
    table = Table(hands, table_card="king", live={"p1": 0})
    table.act("p1", "play_cards", card_ids=["Q1"])

    table.act("p2", "call_liar")

    assert table.of_type("players_eliminated") == [{"players": ["p1"]}]
    assert table.state.alive == ["p2", "p3"]
    assert table.of_type("round_started")[0]["starter"] == "p2"


def test_revolver_risk_rises_pull_by_pull_until_the_live_chamber():
    """A seat with its live chamber at position 3 survives pulls 1-3 and falls on pull 4."""
    table = Table({"p1": ["Q1"], "p2": ["K2"]}, table_card="king", live={"p1": 3, "p2": 5})
    outcomes = []
    for _ in range(4):
        table.state.hands = {"p1": ["Q1", "K1"], "p2": ["K2", "K3"]}
        table.state.current, table.state.phase, table.state.last_play = "p1", "turn", None
        table.act("p1", "play_cards", card_ids=["Q1"])
        table.act("p2", "call_liar")
        outcomes.append(table.of_type("trigger_pulled")[-1]["live"])
        if table.state.phase == "over":
            break

    assert outcomes == [False, False, False, True]
    assert table.state.phase == "over"
    assert table.of_type("match_over") == [{"winner": "p2"}]


def test_results_rank_by_reverse_elimination():
    plugin = LiarsDeck()
    table = Table({"p1": [], "p2": [], "p3": [], "p4": []})
    table.state.alive = ["p3"]
    table.state.eliminated = [["p1"], ["p2", "p4"]]

    placements = plugin.results(table.state)

    assert {(p.player, p.rank) for p in placements} == {("p3", 1), ("p2", 2), ("p4", 2), ("p1", 4)}


# --- special cases ----------------------------------------------------------------


def test_no_call_on_the_first_turn():
    table = Table({"p1": ["K1"], "p2": ["K2"]})

    assert "call_liar" not in [tool.name for tool in table.plugin.get_tools(table.state, "p1")]
    assert table.problem("p1", "call_liar") == (
        "There is no play to call 'Liar!' on yet; play cards instead."
    )


def test_a_player_without_cards_is_skipped():
    hands = {"p1": ["K1", "K4"], "p2": ["Q2"], "p3": ["A3", "K3"]}
    table = Table(hands, table_card="king")
    table.act("p1", "play_cards", card_ids=["K1"])
    table.act("p2", "play_cards", card_ids=["Q2"])  # p2 is now out of cards
    table.act("p3", "play_cards", card_ids=["K3"])

    assert table.state.current == "p1"  # p2 is skipped
    table.act("p1", "play_cards", card_ids=["K4"])
    assert table.state.current == "p3"


def test_only_player_with_cards_calls_automatically():
    table = Table({"p1": ["Q1"], "p2": ["K2", "K3"]}, table_card="king")

    table.act("p1", "play_cards", card_ids=["Q1"])  # p1 has no cards left; only p2 has

    assert table.of_type("liar_called") == [{"caller": "p2", "target": "p1", "automatic": True}]
    assert table.of_type("shooters_chosen")[0]["players"] == ["p1"]


def test_a_play_that_leaves_nobody_else_with_cards_is_checked_by_the_next_player():
    """Defensive case: normal play never gets here, because the last holder calls first."""
    table = Table({"p1": ["K1", "K2"], "p2": [], "p3": []}, table_card="king")

    table.act("p1", "play_cards", card_ids=["K1"])

    assert table.of_type("liar_called") == [{"caller": "p2", "target": "p1", "automatic": True}]


def test_last_card_played_by_the_second_last_holder_is_checked_automatically():
    hands = {"p1": ["K1", "K2"], "p2": ["K3"], "p3": ["K4"]}
    table = Table(hands, table_card="king")
    table.act("p1", "play_cards", card_ids=["K1"])
    table.act("p2", "play_cards", card_ids=["K3"])

    table.act("p3", "play_cards", card_ids=["K4"])  # now only p1 holds cards

    assert table.of_type("liar_called") == [{"caller": "p1", "target": "p3", "automatic": True}]


def test_table_talk_is_once_per_turn_and_does_not_end_it():
    table = Table({"p1": ["K1"], "p2": ["K2"]})

    table.act("p1", "table_talk", text="Kings all round.")

    assert table.state.current == "p1"
    assert {"player": "p1", "text": "Kings all round."} in table.of_type(MESSAGE)
    assert "table_talk" not in [tool.name for tool in table.plugin.get_tools(table.state, "p1")]
    assert table.problem("p1", "table_talk", text="Again") == (
        "You already talked this turn; now play cards or call 'Liar!'."
    )
    table.act("p1", "play_cards", card_ids=["K1"])
    assert "table_talk" in [tool.name for tool in table.plugin.get_tools(table.state, "p2")]


@pytest.mark.parametrize("tool", ["table_talk", "call_liar"])
def test_texts_have_at_most_40_words(tool):
    table = Table({"p1": ["K1"], "p2": ["K2"]})
    table.act("p1", "play_cards", card_ids=["K1"])

    problem = table.problem("p2", tool, text=" ".join(["word"] * 41))

    assert problem == "Your text has 41 words; say it in at most 40."


def test_playing_cards_not_in_hand_is_explained():
    table = Table({"p1": ["K1", "Q1"], "p2": ["K2"]})

    assert table.problem("p1", "play_cards", card_ids=["K2"]) == (
        "You do not hold K2. Your hand is K1, Q1; play ids from it."
    )


def test_claim_text_becomes_a_public_message():
    table = Table({"p1": ["K1"], "p2": ["K2"]})

    table.act("p1", "play_cards", card_ids=["K1"], claim_text="One king.")

    assert table.of_type(MESSAGE) == [{"player": "p1", "text": "One king."}]
    assert table.of_type("cards_played") == [{"player": "p1", "count": 1}]


# --- devil card ------------------------------------------------------------------


def test_revealed_devil_card_makes_everyone_else_shoot_instead():
    hands = {"p1": [DEVIL_ID, "Q1"], "p2": ["K2"], "p3": ["K3"]}
    table = Table(hands, table_card="king", variant="devil_card", live={"p2": 0, "p3": 4})
    table.act("p1", "play_cards", card_ids=[DEVIL_ID])

    table.act("p2", "call_liar")

    revealed = table.of_type("cards_revealed")[0]
    assert revealed["devil"] is True and revealed["honest"] is True
    assert table.of_type("shooters_chosen") == [{"players": ["p2", "p3"], "reason": "devil_card"}]
    assert [p["player"] for p in table.of_type("trigger_pulled")] == ["p2", "p3"]
    assert table.state.pulls["p1"] == 0
    assert table.of_type("players_eliminated") == [{"players": ["p2"]}]
    assert table.of_type("round_started")[0]["starter"] == "p1"


def test_devil_card_with_a_lie_still_spares_its_player():
    hands = {"p1": [DEVIL_ID, "Q1", "K1"], "p2": ["K2"]}
    table = Table(hands, table_card="king", variant="devil_card")
    table.act("p1", "play_cards", card_ids=[DEVIL_ID, "Q1"])

    table.act("p2", "call_liar")

    assert table.of_type("shooters_chosen") == [{"players": ["p2"], "reason": "devil_card"}]


def test_simultaneous_eliminations_share_a_rank():
    hands = {"p1": [DEVIL_ID], "p2": ["K2"], "p3": ["K3"]}
    table = Table(hands, variant="devil_card", live={"p2": 0, "p3": 0})
    table.act("p1", "play_cards", card_ids=[DEVIL_ID])

    table.act("p2", "call_liar")

    assert table.state.phase == "over"
    ranks = {(p.player, p.rank) for p in table.plugin.results(table.state)}
    assert ranks == {("p1", 1), ("p2", 2), ("p3", 2)}


def test_devil_card_id_is_only_shown_in_the_devil_variant():
    base = Table({"p1": ["K1"], "p2": ["K2"]})
    devil = Table({"p1": ["K1"], "p2": ["K2"]}, variant="devil_card")

    assert "devil_card_id" not in base.plugin.get_observation(base.state, "p1")
    assert devil.plugin.get_observation(devil.state, "p1")["devil_card_id"] == DEVIL_ID


# --- hidden information ---------------------------------------------------------


class Spy:
    """A random bot that keeps every request it gets."""

    def __init__(self, plugin, rng):
        self.bot = RandomBot(plugin, rng)
        self.requests: list[TurnRequest] = []

    async def act(self, request: TurnRequest) -> Reply:
        self.requests.append(request)
        return await self.bot.act(request)


@pytest.mark.parametrize("variant", ["base", "devil_card"])
@pytest.mark.parametrize("seed", [1, 2, 3])
def test_no_player_ever_sees_hidden_cards_or_chambers(variant, seed):
    plugin = LiarsDeck()
    spies = {p: Spy(plugin, derive_rng(seed, "spy", p)) for p in SEATS}
    match = Match(plugin, spies, seed=seed, settings={"variant": variant})
    asyncio.run(match.run())

    for player, spy in spies.items():
        assert spy.requests, player
        for request in spy.requests:
            for event in request.events:
                assert event.type != "revolver_loaded"
                if event.type in ("hand_dealt", "cards_hidden"):
                    assert event.data["player"] == player
            assert "live" not in keys(request.observation)
            own = {
                card
                for e in request.events
                if e.type == "hand_dealt" and e.data["player"] == player
                for card in e.data["cards"]
            }
            assert set(request.observation["hand"]) <= own
            # Other players' cards appear only once a call has revealed them.
            for e in request.events:
                if e.type == "hand_dealt":
                    assert e.data["player"] == player


def keys(value):
    """Every dict key anywhere in a nested value."""
    if isinstance(value, dict):
        return set(value) | {k for v in value.values() for k in keys(v)}
    if isinstance(value, list):
        return {k for v in value for k in keys(v)}
    return set()


def test_observation_is_a_copy():
    table = Table({"p1": ["K1"], "p2": ["K2"]})
    observation = table.plugin.get_observation(table.state, "p1")

    observation["hand"].append("A9")
    observation["players"][0]["cards"] = 99

    assert table.state.hands["p1"] == ["K1"]


# --- whole matches ----------------------------------------------------------------


@pytest.mark.parametrize("variant", ["base", "devil_card"])
def test_same_seed_same_match(variant):
    first, first_places = bot_match(SEATS, seed=9, variant=variant)
    second, second_places = bot_match(SEATS, seed=9, variant=variant)
    other, _ = bot_match(SEATS, seed=10, variant=variant)

    assert first.events == second.events
    assert first_places == second_places
    assert first.events != other.events


@pytest.mark.parametrize("variant", ["base", "devil_card"])
def test_replay_rebuilds_the_end_state(variant):
    match, _ = bot_match(SEATS[:3], seed=4, variant=variant)

    assert replay(LiarsDeck(), match.events) == match.state


def test_200_random_bot_matches_end_with_one_survivor():
    rng = random.Random(0)
    for number in range(200):
        players = SEATS[: rng.randint(2, 4)]
        variant = rng.choice(["base", "devil_card"])
        match, placements = bot_match(players, seed=number, variant=variant)

        assert len(match.state.alive) == 1, (number, variant)
        assert sorted(p.player for p in placements) == sorted(players)
        assert [p.rank for p in placements if p.rank == 1] == [1]


def test_render_spec_shows_every_hand_to_spectators():
    table = Table({"p1": ["K1", "Q1"], "p2": ["A2"]})

    spec = table.plugin.render_spec(table.state)

    assert spec["layout"] == "card_table"
    assert [seat["hand"] for seat in spec["seats"]] == [["K1", "Q1"], ["A2"]]
    assert "live" not in keys(spec)
