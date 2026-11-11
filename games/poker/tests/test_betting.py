import random

import pytest

from games.poker.betting import Pot, Street, side_pots, split


def street(stacks, *, posted=None, big_blind=20, order=None):
    """A betting round; `stacks` are chips before any posted bets."""
    order = order or list(stacks)
    posted = posted or {}
    behind = {p: stacks[p] - posted.get(p, 0) for p in order}
    return Street.open(order, behind, big_blind=big_blind, posted=posted)


def act(round_, *moves):
    for move in moves:
        player, kind, *amount = move
        problem = round_.problem(player, kind, *amount)
        assert problem is None, (move, problem)
        round_.apply(player, kind, *amount)


def chips(round_):
    return sum(round_.stacks.values()) + sum(round_.bets.values())


# --- side pots --------------------------------------------------------------------


def test_no_all_in_is_one_pot():
    assert side_pots({"a": 100, "b": 100, "c": 100}, folded=[]) == [Pot(300, ("a", "b", "c"))]


def test_two_all_ins_with_unequal_stacks():
    # a is all-in for 50, b covers with 200, c folds after putting in 20.
    pots = side_pots({"a": 50, "b": 200, "c": 20}, folded=["c"])

    assert pots == [Pot(120, ("a", "b")), Pot(150, ("b",))]  # 150 is b's uncalled bet


def test_three_all_ins_with_unequal_stacks():
    pots = side_pots({"a": 100, "b": 250, "c": 400, "d": 400}, folded=[])

    assert pots == [
        Pot(400, ("a", "b", "c", "d")),
        Pot(450, ("b", "c", "d")),
        Pot(300, ("c", "d")),
    ]


def test_four_all_ins_with_unequal_stacks():
    pots = side_pots({"a": 30, "b": 80, "c": 150, "d": 300, "e": 300}, folded=[])

    assert [p.amount for p in pots] == [150, 200, 210, 300]
    assert [p.eligible for p in pots] == [
        ("a", "b", "c", "d", "e"),
        ("b", "c", "d", "e"),
        ("c", "d", "e"),
        ("d", "e"),
    ]
    assert sum(p.amount for p in pots) == 860


def test_folded_chips_above_every_live_player_go_to_the_last_pot():
    # c raised big and folded to an all-in it could not see; its chips stay in.
    pots = side_pots({"a": 40, "b": 40, "c": 100}, folded=["c"])

    assert pots == [Pot(180, ("a", "b"))]


def test_equal_all_ins_share_one_pot():
    assert side_pots({"a": 100, "b": 100, "c": 300}, folded=[]) == [
        Pot(300, ("a", "b", "c")),
        Pot(200, ("c",)),
    ]


def test_random_contributions_conserve_chips_and_order():
    rng = random.Random(7)
    for _ in range(500):
        players = [f"p{i}" for i in range(rng.randint(2, 6))]
        contributions = {p: rng.choice([0, 10, 20, 50, 120, 300, 1000]) for p in players}
        folded = [p for p in players if rng.random() < 0.3]
        if all(p in folded or contributions[p] == 0 for p in players):
            continue

        pots = side_pots(contributions, folded)

        assert sum(p.amount for p in pots) == sum(contributions.values())
        for pot in pots:
            assert pot.eligible and not set(pot.eligible) & set(folded)
            assert list(pot.eligible) == [p for p in players if p in pot.eligible]


# --- splitting --------------------------------------------------------------------


def test_split_evenly():
    assert split(300, ["a", "b", "c"]) == {"a": 100, "b": 100, "c": 100}


def test_odd_chips_go_to_the_first_winners_in_order():
    assert split(101, ["b", "a"]) == {"b": 51, "a": 50}
    assert split(302, ["c", "a", "b"]) == {"c": 101, "a": 101, "b": 100}


def test_a_pot_needs_a_winner():
    with pytest.raises(ValueError, match="at least one winner"):
        split(10, [])


# --- a betting round ----------------------------------------------------------------


def test_preflop_min_raise_is_double_the_big_blind():
    round_ = street(
        {"utg": 1000, "sb": 1000, "bb": 1000},
        posted={"sb": 10, "bb": 20},
        order=["utg", "sb", "bb"],
    )

    legal = round_.legal("utg")

    assert (legal.call_amount, legal.min_raise_to, legal.max_raise_to) == (20, 40, 1000)
    assert round_.problem("utg", "raise", 30) == (
        "The minimum raise is to 40 (the bet of 20 plus the last raise of 20)."
    )


def test_min_raise_follows_the_last_raise_size():
    round_ = street({"a": 1000, "b": 1000, "c": 1000}, posted={"b": 10, "c": 20})
    act(round_, ("a", "raise", 70))  # a raise of 50

    assert round_.legal("b").min_raise_to == 120
    act(round_, ("b", "raise", 120))
    assert round_.legal("c").min_raise_to == 170


def test_round_ends_when_everyone_matched_or_folded():
    round_ = street({"a": 1000, "b": 1000, "c": 1000}, posted={"b": 10, "c": 20})

    act(round_, ("a", "call"), ("b", "call"))
    assert round_.next_actor() == "c"  # the big blind may still raise
    act(round_, ("c", "check"))

    assert round_.next_actor() is None
    assert round_.bets == {"a": 20, "b": 20, "c": 20}


def test_a_raise_reopens_the_action_for_everyone_else():
    round_ = street({"a": 1000, "b": 1000, "c": 1000})
    act(round_, ("a", "check"), ("b", "raise", 50))

    assert round_.to_act == ["c", "a"]


def test_a_short_all_in_does_not_reopen_raising():
    round_ = street({"a": 1000, "b": 1000, "c": 130})
    act(round_, ("a", "raise", 100), ("b", "call"), ("c", "all_in"))  # c adds only 30 more

    assert round_.to_act == ["a", "b"]
    assert round_.legal("a").min_raise_to is None
    assert round_.problem("a", "raise", 300) == "You may not raise now; call or fold."
    act(round_, ("a", "call"), ("b", "call"))
    assert round_.next_actor() is None


def test_a_full_all_in_raise_reopens_raising():
    round_ = street({"a": 1000, "b": 1000, "c": 200})
    act(round_, ("a", "raise", 100), ("b", "call"), ("c", "all_in"))  # a full raise of 100

    assert round_.legal("a").min_raise_to == 300


def test_a_short_stack_can_call_for_less():
    round_ = street({"a": 1000, "b": 60})
    act(round_, ("a", "raise", 200))

    assert round_.legal("b").call_amount == 60
    act(round_, ("b", "call"))
    assert round_.all_in == ["b"] and round_.next_actor() is None


def test_raise_cannot_exceed_the_stack():
    round_ = street({"a": 100, "b": 1000})

    assert round_.problem("a", "raise", 150) == (
        "You have only 100 chips in total; raise to at most that."
    )


def test_check_and_call_mistakes_are_explained():
    round_ = street({"a": 1000, "b": 1000}, posted={"a": 10, "b": 20})

    assert round_.problem("a", "check") == "You cannot check: 10 to call. Call, raise or fold."
    act(round_, ("a", "call"))
    assert round_.problem("b", "call") == "There is nothing to call; check instead."
    assert round_.problem("a", "check") == "It is not your turn; b acts now."


def test_folding_to_one_player_ends_the_round():
    round_ = street({"a": 1000, "b": 1000, "c": 1000}, posted={"b": 10, "c": 20})
    act(round_, ("a", "fold"), ("b", "fold"))

    assert round_.live() == ["c"]
    assert round_.next_actor() is None


def test_no_round_when_at_most_one_player_can_bet():
    round_ = Street.open(["a", "b"], {"a": 0, "b": 500}, big_blind=20, all_in=["a"])

    assert round_.next_actor() is None


def test_random_rounds_conserve_chips():
    rng = random.Random(3)
    for _ in range(300):
        players = [f"p{i}" for i in range(rng.randint(2, 6))]
        stacks = {p: rng.choice([15, 40, 200, 1000]) for p in players}
        round_ = street(
            stacks,
            posted={
                players[0]: min(10, stacks[players[0]]),
                players[1]: min(20, stacks[players[1]]),
            },
        )
        total = chips(round_)
        steps = 0
        while (player := round_.next_actor()) is not None:
            legal = round_.legal(player)
            options = ["fold", "all_in", "check" if legal.can_check else "call"]
            if legal.min_raise_to is not None:
                options.append("raise")
            kind = rng.choice(options)
            amount = (
                rng.randint(legal.min_raise_to, legal.max_raise_to) if kind == "raise" else None
            )
            assert round_.problem(player, kind, amount) is None
            round_.apply(player, kind, amount)
            steps += 1
            assert chips(round_) == total
            assert steps < 100
        live_bets = {round_.bets[p] for p in round_.live() if p not in round_.all_in}
        assert len(live_bets) <= 1  # everyone still betting has matched
