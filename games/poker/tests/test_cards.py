import random

import pytest

from arena.engine.rng import derive_rng
from games.poker.cards import FULL_DECK, Card, Deck, format_cards, parse_cards


def test_full_deck_has_52_distinct_cards():
    assert len(FULL_DECK) == 52
    assert len(set(FULL_DECK)) == 52
    assert {card.rank for card in FULL_DECK} == set(range(2, 15))
    assert {card.suit for card in FULL_DECK} == set("cdhs")


def test_every_card_round_trips_through_text():
    for card in FULL_DECK:
        assert Card.parse(str(card)) == card


def test_parse_and_format():
    cards = parse_cards("Ah Td 2c")

    assert cards == [Card(14, "h"), Card(10, "d"), Card(2, "c")]
    assert format_cards(cards) == "Ah Td 2c"


@pytest.mark.parametrize("text", ["", "A", "10h", "Ax", "1h", "ah", "AhK"])
def test_bad_card_text_is_rejected(text: str):
    with pytest.raises(ValueError, match="not a card"):
        Card.parse(text)


@pytest.mark.parametrize(("rank", "suit"), [(1, "h"), (15, "h"), (10, "x"), (10, "hd")])
def test_bad_card_values_are_rejected(rank: int, suit: str):
    with pytest.raises(ValueError, match="not a card"):
        Card(rank, suit)


def test_same_seed_deals_the_same_cards():
    first = Deck(derive_rng(7, "deck", 1)).deal(52)
    second = Deck(derive_rng(7, "deck", 1)).deal(52)
    other_hand = Deck(derive_rng(7, "deck", 2)).deal(52)

    assert first == second
    assert first != other_hand
    assert sorted(first, key=str) == sorted(FULL_DECK, key=str)


def test_dealing_takes_cards_off_the_top():
    deck = Deck(random.Random(1))

    hole = deck.deal(2)
    flop = deck.deal(3)

    assert len(deck) == 47
    assert not set(hole) & set(flop)
    assert len(deck.deal(47)) == 47
    with pytest.raises(ValueError, match="cannot deal 1 cards, 0 left"):
        deck.deal()
