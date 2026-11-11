"""Diplomacy: messages, treaties, wars, reputation, tributes and trade."""

import json
from decimal import Decimal

import pytest

from arena.engine.types import MESSAGE, Event
from games.civ import diplomacy as d
from games.civ.state import CivState, new_game
from games.civ.tests.realm import CENTER, DATA, RICH, Realm, bare_map, reordered
from games.civ.turn import apply_event

THREE = ("ada", "bo", "cy")


def realm(players=THREE, **stock) -> Realm:
    world = Realm(bare_map(), players)
    world.start_round()
    for player in players:
        world.state.nations[player].stock = dict(stock or RICH)
    return world


def sign(world: Realm, a: str, b: str, treaty: str, **terms) -> str:
    offer = d.propose_treaty(world.state, DATA, world.ctx, a, b, treaty, **terms)
    return d.respond_treaty(world.state, DATA, world.ctx, b, offer, True)


def agree(world: Realm, a: str, b: str, gives: dict, wants: dict, rounds: int = 1) -> str:
    offer = d.propose_trade(world.state, DATA, world.ctx, a, b, gives, wants, rounds)
    d.respond_trade(world.state, DATA, world.ctx, b, offer, True)
    return offer


def last(world: Realm) -> Event:
    return world.events[-1]


# --- messages ---------------------------------------------------------------


def test_a_message_is_the_engine_message_public_or_private_to_the_two():
    world = realm()

    d.message(world.state, world.ctx, "ada", "Peace in our time?")
    assert (last(world).type, last(world).data, last(world).visible_to) == (
        MESSAGE,
        {"player": "ada", "text": "Peace in our time?"},
        None,
    )
    d.message(world.state, world.ctx, "ada", "Only you and me.", to="bo")
    assert last(world).visible_to == ("ada", "bo")


@pytest.mark.parametrize(
    ("text", "to", "problem"),
    [
        ("hi", "ada", "'ada' is not another nation. The others: bo, cy."),
        ("hi", "zed", "'zed' is not another nation"),
        ("   ", None, "The message is empty."),
        ("x" * (d.MESSAGE_CHARS + 1), None, f"at most {d.MESSAGE_CHARS} are sent"),
    ],
)
def test_a_message_needs_words_a_length_limit_and_another_nation(text, to, problem):
    assert problem in d.message_problem(realm().state, "ada", text, to)


# --- treaties ---------------------------------------------------------------


def test_an_offer_is_private_and_a_signed_treaty_is_public():
    world = realm()

    offer = d.propose_treaty(world.state, DATA, world.ctx, "ada", "bo", "non_aggression", rounds=5)
    assert (offer, last(world).visible_to) == ("o1", ("ada", "bo"))
    assert world.state.offers[0].rounds == 5

    treaty = d.respond_treaty(world.state, DATA, world.ctx, "bo", offer, True)
    signed = last(world)
    assert (treaty, signed.type, signed.visible_to) == ("t1", "treaty_signed", None)
    assert signed.data["parties"] == ["ada", "bo"]
    assert world.state.offers == []
    (pact,) = world.state.treaties
    # Signed in round 1 for 5 rounds: it holds in rounds 1 to 5.
    assert (pact.kind, pact.ends_round) == ("non_aggression", 5)


def test_a_treaty_without_rounds_takes_its_default_length_and_ends_when_it_runs_out():
    world = realm()
    sign(world, "ada", "bo", "open_borders")
    default = DATA.treaties["open_borders"].duration_rounds.default
    assert world.state.treaties[0].ends_round == default

    for _ in range(default - 1):
        world.round()
    assert world.state.treaties and world.state.round == default
    world.round()

    assert world.state.treaties == []
    assert world.of_type("treaty_expired") == [{"treaty": "t1"}]


def test_peace_and_alliance_last_until_broken():
    world = realm()
    sign(world, "ada", "bo", "alliance")

    for _ in range(40):
        world.round()

    assert world.state.treaties[0].ends_round is None
    assert d.treaty_problem(world.state, DATA, "ada", "cy", "peace", rounds=3) == (
        "A Peace lasts until it is broken; leave out the rounds."
    )


def test_a_declined_or_unanswered_offer_goes_away():
    world = realm()
    first = d.propose_treaty(world.state, DATA, world.ctx, "ada", "bo", "peace")
    d.propose_treaty(world.state, DATA, world.ctx, "ada", "cy", "peace")

    d.respond_treaty(world.state, DATA, world.ctx, "bo", first, False)
    assert last(world).type == "treaty_declined"
    assert [o.id for o in world.state.offers] == ["o2"]

    world.round()  # the next round: the offer can still be answered
    assert [o.id for o in world.state.offers] == ["o2"]
    world.round()  # the round after: it lapses
    assert world.state.offers == []
    assert world.of_type("offer_lapsed") == [{"offer": "o2"}]
    assert d.answer_problem(world.state, DATA, "cy", "o2", True, "treaty") == (
        "There is no open treaty offer 'o2' to you. Open treaty offers: none."
    )


def test_only_the_nation_offered_can_answer():
    world = realm()
    offer = d.propose_treaty(world.state, DATA, world.ctx, "ada", "bo", "peace")

    assert "no open treaty offer 'o1' to you" in d.answer_problem(
        world.state, DATA, "ada", offer, True, "treaty"
    )
    assert "no open trade offer" in d.answer_problem(world.state, DATA, "bo", offer, True, "trade")


@pytest.mark.parametrize(
    ("terms", "problem"),
    [
        ({"treaty": "friendship"}, "There is no treaty 'friendship'. Treaties: peace,"),
        ({"treaty": "non_aggression", "rounds": 2}, "lasts 3 to 30 rounds, not 2"),
        ({"treaty": "non_aggression", "rounds": 31}, "lasts 3 to 30 rounds, not 31"),
        ({"treaty": "tribute", "payment": {"gold": 5}}, "Say who pays the Tribute: ada or bo."),
        ({"treaty": "tribute", "payer": "bo"}, "A tribute needs a payment per round"),
        ({"treaty": "tribute", "payer": "bo", "payment": {"jade": 1}}, "'jade' is not a resource"),
        ({"treaty": "tribute", "payer": "bo", "payment": {"gold": 0}}, "at least 1, not 0"),
        ({"treaty": "peace", "payer": "bo"}, "A Peace has no payment"),
    ],
)
def test_a_bad_treaty_offer_says_how_to_fix_it(terms, problem):
    assert problem in d.treaty_problem(realm().state, DATA, "ada", "bo", **terms)


def test_a_treaty_of_a_kind_the_two_already_have_is_refused():
    world = realm()
    sign(world, "ada", "bo", "open_borders")

    assert d.treaty_problem(world.state, DATA, "bo", "ada", "open_borders") == (
        "You already have a Open Borders with ada."
    )
    assert d.treaty_problem(world.state, DATA, "bo", "ada", "peace") is None


def test_at_war_only_peace_can_be_offered_and_peace_ends_the_war():
    world = realm()
    d.declare_war(world.state, DATA, world.ctx, "ada", "bo")

    assert d.treaty_problem(world.state, DATA, "bo", "ada", "alliance") == (
        "You are at war with ada: offer peace first."
    )
    sign(world, "bo", "ada", "peace")

    assert last(world).data["ends_war"] is True
    assert not d.at_war(world.state, "ada", "bo")
    assert world.state.wars == []


def test_an_offer_that_became_illegal_cannot_be_accepted():
    world = realm()
    offer = d.propose_treaty(world.state, DATA, world.ctx, "ada", "bo", "alliance")
    d.declare_war(world.state, DATA, world.ctx, "bo", "ada")

    assert d.answer_problem(world.state, DATA, "bo", offer, True, "treaty") == (
        "The offer cannot be signed now: You are at war with bo: offer peace first."
    )
    # Declining is always possible.
    d.respond_treaty(world.state, DATA, world.ctx, "bo", offer, False)


def test_a_tribute_pays_every_round_what_the_payer_has_up_to_the_amount():
    world = realm()
    sign(world, "ada", "bo", "tribute", rounds=3, payer="bo", payment={"gold": 5, "iron": 2})
    world.state.nations["bo"].stock = {"food": 99, "wood": 99, "iron": 1, "gold": 99}

    d.settle(world.state, DATA, world.ctx)

    (paid,) = world.of_type("tribute_paid")
    assert paid == {"treaty": "t1", "payer": "bo", "payee": "ada", "paid": {"gold": 5, "iron": 1}}
    assert world.events[-1].visible_to == ("bo", "ada")
    assert world.stock("bo")["iron"] == 0 and world.stock("ada")["gold"] == RICH["gold"] + 5


# --- breaking, war and reputation ------------------------------------------


def test_breaking_a_treaty_is_public_and_costs_reputation():
    world = realm()
    sign(world, "ada", "bo", "non_aggression")

    d.break_treaty(world.state, DATA, world.ctx, "bo", "t1")

    broken = last(world)
    assert (broken.type, broken.visible_to) == ("treaty_broken", None)
    assert broken.data == {"treaty": "t1", "by": "bo", "reputation": 30}
    assert world.state.nations["bo"].reputation == 30
    assert world.state.nations["ada"].reputation == DATA.reputation.start
    assert world.state.treaties == []


def test_reputation_never_falls_below_its_floor():
    world = realm()
    for _ in range(4):
        sign(world, "ada", "bo", "peace")
        d.break_treaty(world.state, DATA, world.ctx, "ada", world.state.treaties[0].id)

    assert world.state.nations["ada"].reputation == DATA.reputation.min == 0


def test_only_a_party_can_break_a_treaty():
    world = realm()
    sign(world, "ada", "bo", "peace")

    assert d.break_problem(world.state, "cy", "t1") == (
        "You have no treaty 't1'. Your treaties: none."
    )


def test_war_breaks_every_treaty_between_the_two_and_each_costs_reputation():
    world = realm()
    sign(world, "ada", "bo", "non_aggression")
    sign(world, "ada", "bo", "open_borders")
    sign(world, "ada", "cy", "peace")
    assert d.may_attack(world.state, DATA, "ada", "bo").startswith(
        "Your Non-Aggression Pact with bo (t1) forbids an attack."
    )

    d.declare_war(world.state, DATA, world.ctx, "ada", "bo")

    war = last(world)
    assert (war.type, war.visible_to) == ("war_declared", None)
    assert war.data == {
        "by": "ada",
        "on": "bo",
        "broken": ["t1", "t2"],
        "joined": [],
        "reputation": 10,
    }
    assert [pact.id for pact in world.state.treaties] == ["t3"]
    assert (
        d.at_war(world.state, "bo", "ada") and d.may_attack(world.state, DATA, "ada", "bo") is None
    )
    assert d.wars_of(world.state, "ada") == ["bo"]
    assert d.war_problem(world.state, "bo", "ada") == "You are already at war with ada."


def test_the_allies_of_the_attacked_join_unless_a_treaty_binds_them_to_the_attacker():
    world = realm(("ada", "bo", "cy", "di"))
    sign(world, "bo", "cy", "alliance")
    sign(world, "bo", "di", "alliance")
    sign(world, "di", "ada", "non_aggression")

    d.declare_war(world.state, DATA, world.ctx, "ada", "bo")

    assert last(world).data["joined"] == ["cy"]
    assert d.wars_of(world.state, "ada") == ["bo", "cy"]
    assert not d.at_war(world.state, "ada", "di")
    # The declarer broke no treaty with the ones who joined: its reputation is untouched.
    assert world.state.nations["ada"].reputation == DATA.reputation.start


def test_an_alliance_shares_sight_and_borders_and_open_borders_only_borders():
    world = realm()
    sign(world, "ada", "bo", "alliance")
    sign(world, "ada", "cy", "open_borders")

    assert d.allies(world.state, DATA, "ada") == ["bo"]
    assert d.allies(world.state, DATA, "cy") == []
    assert d.open_borders(world.state, DATA, "bo", "ada")
    assert d.open_borders(world.state, DATA, "cy", "ada")
    assert not d.open_borders(world.state, DATA, "bo", "cy")


# --- trade ------------------------------------------------------------------


def test_an_agreed_trade_is_carried_out_in_the_trade_step_with_a_fee_on_each_side():
    world = realm()
    agree(world, "ada", "bo", {"wood": 20}, {"gold": 10})

    assert world.stock("ada")["wood"] == RICH["wood"]  # nothing moves before the trade step
    d.settle(world.state, DATA, world.ctx)

    done = last(world)
    assert (done.type, done.visible_to) == ("trade_done", ("ada", "bo"))
    # 10 % of 20 wood and of 10 gold, rounded down.
    assert done.data["paid"] == {"ada": {"wood": 22}, "bo": {"gold": 11}}
    assert world.stock("ada")["wood"] == RICH["wood"] - 22
    assert world.stock("ada")["gold"] == RICH["gold"] + 10
    assert world.stock("bo")["wood"] == RICH["wood"] + 20
    assert world.state.deals == []


def test_low_reputation_raises_the_fee_and_a_market_halves_it():
    world = realm()
    world.state.nations["bo"].reputation = DATA.balance.trade.low_reputation_below - 1
    world.found("cy", CENTER, "market")

    assert d.trade_fee(world.state, DATA, "ada") == Decimal("0.1")
    assert d.trade_fee(world.state, DATA, "bo") == Decimal("0.2")
    assert d.trade_fee(world.state, DATA, "cy") == Decimal("0.05")
    assert d.with_fee(world.state, DATA, "bo", {"gold": 10}) == {"gold": 12}


def test_a_trade_over_several_rounds_runs_its_rounds_and_ends():
    world = realm()
    agree(world, "ada", "bo", {"wood": 1}, {}, rounds=3)

    for _ in range(4):
        world.round()

    assert len(world.of_type("trade_done")) == 3
    assert [e["rounds_left"] for e in world.of_type("trade_done")] == [2, 1, 0]
    assert world.state.deals == []


def test_a_trade_that_one_side_cannot_pay_fails_and_ends():
    world = realm()
    agree(world, "ada", "bo", {"wood": 5}, {"gold": 5}, rounds=3)
    world.state.nations["bo"].stock["gold"] = 4

    d.settle(world.state, DATA, world.ctx)

    assert last(world).type == "trade_failed"
    assert last(world).data == {"deal": "o1", "short": ["bo"]}
    assert world.state.deals == []
    assert world.stock("ada")["wood"] == RICH["wood"]


def test_a_trade_offer_checks_what_the_sender_can_pay_and_how_long_it_runs():
    world = realm(food=0, wood=3, iron=0, gold=0)
    state = world.state

    assert d.trade_problem(state, DATA, "ada", "bo", {"wood": 3}, {"gold": 1}) is None
    assert d.trade_problem(state, DATA, "ada", "bo", {"wood": 10}, {}) == (
        "ada needs 11 wood with the trade fee and has 3 wood."
    )
    assert d.trade_problem(state, DATA, "ada", "bo", {}, {}) == (
        "A trade needs something to give or to get."
    )
    assert "runs 1 to 20 rounds, not 21" in d.trade_problem(
        state, DATA, "ada", "bo", {"wood": 1}, {}, 21
    )


def test_war_stops_the_trades_between_the_enemies():
    world = realm()
    agree(world, "ada", "bo", {"wood": 1}, {}, rounds=5)
    agree(world, "ada", "cy", {"wood": 1}, {}, rounds=5)

    d.declare_war(world.state, DATA, world.ctx, "bo", "ada")

    assert [deal.id for deal in world.state.deals] == ["o2"]
    assert d.trade_problem(world.state, DATA, "ada", "bo", {"wood": 1}, {}) == (
        "You are at war with bo: no trade until there is peace."
    )


# --- the log ----------------------------------------------------------------


def test_the_log_rebuilds_the_state_without_data_or_rules():
    world = realm(("ada", "bo", "cy", "di"))
    sign(world, "bo", "cy", "alliance")
    sign(world, "ada", "di", "tribute", payer="di", payment={"gold": 2})
    agree(world, "ada", "bo", {"wood": 2}, {"gold": 1}, rounds=2)
    d.propose_treaty(world.state, DATA, world.ctx, "cy", "di", "peace")
    d.message(world.state, world.ctx, "cy", "I see you.", to="di")
    world.round()
    d.declare_war(world.state, DATA, world.ctx, "ada", "bo")
    d.break_treaty(world.state, DATA, world.ctx, "di", "t2")
    world.round()

    rebuilt = CivState(world=world.state.world, nations=new_game(world.state.nations, DATA).nations)
    for nation in rebuilt.nations.values():
        nation.stock = dict(RICH)  # as realm() set it, outside the log
    for event in world.events:
        stored = reordered(json.loads(json.dumps(event.data)))
        apply_event(rebuilt, Event(source=event.source, type=event.type, data=stored))

    assert rebuilt == world.state
