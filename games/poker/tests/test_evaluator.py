import itertools
import random
from collections import Counter

import pytest

from arena.engine.rng import derive_rng
from games.poker.cards import FULL_DECK, Card, parse_cards
from games.poker.evaluator import HandCategory, best_hand, win_probabilities, winners

C = HandCategory


def hand(text: str):
    return best_hand(parse_cards(text))


def holes(**players: str) -> dict[str, list[Card]]:
    return {name: parse_cards(cards) for name, cards in players.items()}


# --- categories --------------------------------------------------------------


@pytest.mark.parametrize(
    ("cards", "category", "tiebreak"),
    [
        ("Ah Kh Qh Jh Th", C.ROYAL_FLUSH, (14,)),
        ("9s 8s 7s 6s 5s", C.STRAIGHT_FLUSH, (9,)),
        ("Qc Qd Qh Qs 3d", C.FOUR_OF_A_KIND, (12, 3)),
        ("Jc Jd Jh 4s 4d", C.FULL_HOUSE, (11, 4)),
        ("Kd 9d 7d 4d 2d", C.FLUSH, (13, 9, 7, 4, 2)),
        ("Tc 9d 8h 7s 6c", C.STRAIGHT, (10,)),
        ("7c 7d 7h Ks 2c", C.THREE_OF_A_KIND, (7, 13, 2)),
        ("Ac Ad 5h 5s Qc", C.TWO_PAIR, (14, 5, 12)),
        ("8c 8d Ah 6s 3c", C.ONE_PAIR, (8, 14, 6, 3)),
        ("Kc Jd 9h 6s 3c", C.HIGH_CARD, (13, 11, 9, 6, 3)),
    ],
)
def test_every_category(cards: str, category: HandCategory, tiebreak: tuple[int, ...]):
    value = hand(cards)

    assert value.category == category
    assert value.tiebreak == tiebreak


def test_categories_rank_in_spec_order():
    ladder = [
        "Kc Jd 9h 6s 3c",
        "8c 8d Ah 6s 3c",
        "Ac Ad 5h 5s Qc",
        "7c 7d 7h Ks 2c",
        "Tc 9d 8h 7s 6c",
        "Kd 9d 7d 4d 2d",
        "Jc Jd Jh 4s 4d",
        "Qc Qd Qh Qs 3d",
        "9s 8s 7s 6s 5s",
        "Ah Kh Qh Jh Th",
    ]
    values = [hand(cards) for cards in ladder]

    assert values == sorted(values)
    assert len(set(values)) == len(values)


# --- straights ---------------------------------------------------------------


def test_wheel_is_a_five_high_straight():
    wheel = hand("Ac 2d 3h 4s 5c")

    assert wheel.category == C.STRAIGHT
    assert wheel.tiebreak == (5,)
    assert wheel < hand("2c 3d 4h 5s 6c")


def test_broadway_is_the_highest_straight():
    broadway = hand("Ac Kd Qh Js Tc")

    assert broadway.category == C.STRAIGHT
    assert broadway > hand("Kc Qd Jh Ts 9c")


def test_straights_do_not_wrap_around():
    assert hand("Qc Kd Ah 2s 3c").category == C.HIGH_CARD


def test_steel_wheel_is_a_straight_flush_not_royal():
    value = hand("Ah 2h 3h 4h 5h")

    assert value.category == C.STRAIGHT_FLUSH
    assert value.tiebreak == (5,)


def test_longest_run_counts_its_top_five():
    assert hand("4c 5d 6h 7s 8c 9d Th").tiebreak == (10,)


# --- flush vs straight vs straight flush ------------------------------------


def test_flush_and_separate_straight_make_a_flush():
    value = hand("2h 5h 9h Jh Kh Tc Qd")  # straight 9-K is not all hearts

    assert value.category == C.FLUSH
    assert value.tiebreak == (13, 11, 9, 5, 2)


def test_straight_flush_beats_higher_offsuit_straight():
    value = hand("5h 6h 7h 8h 9h Ts Jc")

    assert value.category == C.STRAIGHT_FLUSH
    assert value.tiebreak == (9,)


def test_flush_uses_top_five_of_six_suited():
    assert hand("Ah Jh 9h 6h 4h 2h Kc").tiebreak == (14, 11, 9, 6, 4)


def test_royal_beats_straight_flush_beats_four_of_a_kind():
    assert hand("Ah Kh Qh Jh Th") > hand("Kd Qd Jd Td 9d") > hand("Ac Ad Ah As Kc")


# --- full house, quads -------------------------------------------------------


def test_full_house_compares_trips_first_then_pair():
    assert hand("Kc Kd Kh 2s 2c") > hand("Qc Qd Qh As Ac")
    assert hand("Kc Kd Kh 9s 9c") > hand("Ks Kd Kh 8s 8c")


def test_two_trips_make_a_full_house_with_the_lower_as_pair():
    value = hand("Ac Ad Ah Kc Kd Ks 2c")

    assert value.category == C.FULL_HOUSE
    assert value.tiebreak == (14, 13)


def test_full_house_takes_the_best_pair_of_two():
    assert hand("9c 9d 9h 5s 5c Qd Qh").tiebreak == (9, 12)


def test_quads_take_the_highest_kicker_even_from_a_pair():
    assert hand("6c 6d 6h 6s 2c 2d 9h").tiebreak == (6, 9)


def test_shared_board_full_house_is_decided_by_hole_pair():
    board = parse_cards("7c 7d 7h Ks 2c")

    result = winners(holes(ann="Kc 3d", bob="2d 2h"), board)

    assert result == ["ann"]  # 777KK beats 77722


# --- pairs and kickers -------------------------------------------------------


def test_two_pair_with_the_same_pairs_compares_the_kicker():
    assert hand("Ac Ad Kh Ks Qc") > hand("As Ah Kc Kd Jc")


def test_three_pairs_play_the_top_two_and_best_kicker():
    value = hand("Ac Ad Kh Ks Qc Qd 2c")

    assert value.category == C.TWO_PAIR
    assert value.tiebreak == (14, 13, 12)


def test_kicker_split_when_kickers_do_not_play():
    board = parse_cards("Jc Jd 9h 6s 2c")

    assert winners(holes(ann="Ac 5d", bob="Ah 4c"), board) == ["ann", "bob"]


def test_third_kicker_decides_when_it_plays():
    board = parse_cards("Jc Jd 9h 3s 2c")

    assert winners(holes(ann="Ac 7d", bob="Ah 6c"), board) == ["ann"]


def test_high_card_compares_all_five():
    assert hand("Ac Qd 9h 6s 4c") > hand("Ah Qc 9d 6c 3s")


# --- board plays, ties -------------------------------------------------------


def test_royal_on_the_board_is_a_tie_for_everyone():
    board = parse_cards("Ah Kh Qh Jh Th")

    assert winners(holes(ann="2c 3d", bob="Ac As", cid="9h 8h"), board) == ["ann", "bob", "cid"]


def test_board_straight_extended_by_a_hole_card_wins():
    board = parse_cards("5c 6d 7h 8s 9c")

    assert winners(holes(ann="Tc 2d", bob="Ac Kd"), board) == ["ann"]


def test_same_hand_in_different_suits_is_an_exact_tie():
    board = parse_cards("Kc 8d 7h 4s 2c")

    assert winners(holes(ann="Ah Qh", bob="As Qs"), board) == ["ann", "bob"]
    assert hand("Ah Qh Kc 8d 7h") == hand("As Qs Kc 8d 7h")


def test_winners_keep_the_given_order():
    board = parse_cards("Ah Kh Qh Jh Th")

    assert winners(holes(zed="2c 3d", amy="4c 5d"), board) == ["zed", "amy"]


# --- the five cards ----------------------------------------------------------


def test_best_cards_are_five_of_the_input_and_make_the_same_hand():
    cards = parse_cards("Ac Ad Kh Ks Qc Qd 2c")

    value = best_hand(cards)

    assert len(value.cards) == 5
    assert set(value.cards) <= set(cards)
    assert best_hand(list(value.cards)) == value


# --- bad input ---------------------------------------------------------------


@pytest.mark.parametrize("cards", ["Ac Kd Qh Js", "Ac Kd Qh Js Tc 9d 8h 7s"])
def test_hand_needs_five_to_seven_cards(cards: str):
    with pytest.raises(ValueError, match="need 5 to 7 cards"):
        hand(cards)


def test_duplicate_cards_are_rejected():
    with pytest.raises(ValueError, match="appears twice"):
        hand("Ac Ac Kd Qh Js")
    with pytest.raises(ValueError, match="appears twice"):
        winners(holes(ann="Ac Kd", bob="Ac Qd"), parse_cards("2c 3d 4h 5s 7c"))


def test_showdown_needs_a_full_board():
    with pytest.raises(ValueError, match="needs 5 cards"):
        winners(holes(ann="Ac Kd"), parse_cards("2c 3d 4h"))


# --- against brute force -----------------------------------------------------


def naive_five(cards: tuple[Card, ...]) -> tuple[int, tuple[int, ...]]:
    """Independent reference: classify exactly five cards by rank shape."""
    ranks = sorted((card.rank for card in cards), reverse=True)
    groups = sorted(Counter(ranks).items(), key=lambda rc: (rc[1], rc[0]), reverse=True)
    shape = [count for _, count in groups]
    ordered = tuple(rank for rank, _ in groups)
    flush = len({card.suit for card in cards}) == 1
    distinct = sorted(set(ranks))
    straight = None
    if len(distinct) == 5 and distinct[4] - distinct[0] == 4:
        straight = distinct[4]
    elif distinct == [2, 3, 4, 5, 14]:
        straight = 5
    if straight and flush:
        return (9 if straight == 14 else 8, (straight,))
    if shape == [4, 1]:
        return 7, ordered
    if shape == [3, 2]:
        return 6, ordered
    if flush:
        return 5, tuple(ranks)
    if straight:
        return 4, (straight,)
    if shape == [3, 1, 1]:
        return 3, ordered
    if shape == [2, 2, 1]:
        return 2, ordered
    if shape == [2, 1, 1, 1]:
        return 1, ordered
    return 0, tuple(ranks)


@pytest.mark.parametrize("size", [5, 6, 7])
def test_matches_brute_force_over_every_five_card_subset(size: int):
    rng = random.Random(size)
    seen = Counter()
    for _ in range(10_000):
        cards = rng.sample(FULL_DECK, size)

        value = best_hand(cards)

        expected = max(naive_five(five) for five in itertools.combinations(cards, 5))
        assert (value.category, value.tiebreak) == expected, cards
        assert naive_five(value.cards) == expected, cards
        seen[value.category] += 1
    assert len(seen) >= 7  # random hands hit the common categories; rare ones are below


def test_rare_categories_match_brute_force():
    rng = random.Random(0)
    for cards_text in ["Ah Kh Qh Jh Th", "Ah 2h 3h 4h 5h", "9c 9d 9h 9s"]:
        base = parse_cards(cards_text)
        rest = [card for card in FULL_DECK if card not in base]
        for _ in range(200):
            cards = base + rng.sample(rest, 7 - len(base))
            expected = max(naive_five(five) for five in itertools.combinations(cards, 5))
            value = best_hand(cards)
            assert (value.category, value.tiebreak) == expected, cards


# --- win probabilities -------------------------------------------------------


def test_aces_against_seven_deuce_win_about_seven_in_eight():
    players = holes(aces="As Ah", junk="7c 2d")

    shares = win_probabilities(players, [], derive_rng(1, "equity"), samples=4000)

    assert 0.84 < shares["aces"] < 0.91
    assert shares["aces"] + shares["junk"] == pytest.approx(1)


def test_same_seed_gives_the_same_estimate():
    players = holes(ann="Kc Qc", bob="9d 9h", cid="As 5s")
    board = parse_cards("Jc 9s 2c")

    first = win_probabilities(players, board, derive_rng(3, "equity"), samples=500)
    second = win_probabilities(players, board, derive_rng(3, "equity"), samples=500)

    assert first == second


def test_turn_is_counted_exactly():
    # Bob has trips; Ann wins only with one of the two remaining aces out of 44 cards.
    players = holes(ann="Ah Ad", bob="Kh Kd")
    board = parse_cards("Kc 7s 2c 3d")

    shares = win_probabilities(players, board, random.Random(0), samples=100)

    assert shares == {"ann": pytest.approx(2 / 44), "bob": pytest.approx(42 / 44)}


def test_complete_board_gives_the_result():
    board = parse_cards("Kc 8d 7h 4s 2c")

    assert win_probabilities(holes(ann="Ah Qh", bob="As Qs"), board, random.Random(0)) == {
        "ann": 0.5,
        "bob": 0.5,
    }
    assert win_probabilities(holes(ann="Kd Kh", bob="As Qs"), board, random.Random(0)) == {
        "ann": 1.0,
        "bob": 0.0,
    }


def test_estimate_rejects_bad_input():
    with pytest.raises(ValueError, match="at most 5"):
        win_probabilities(holes(ann="Ah Ad"), parse_cards("2c 3c 4c 5c 6c 7c"), random.Random())
    with pytest.raises(ValueError, match="appears twice"):
        win_probabilities(holes(ann="Ah Ad", bob="Ah Kd"), [], random.Random())
