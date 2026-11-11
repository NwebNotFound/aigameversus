"""Playing cards and a seeded 52-card deck.

A card is written as rank then suit, for example ``Ah`` (ace of hearts) or
``Td`` (ten of diamonds). That text form is what goes into events and
observations, so they stay plain JSON.
"""

from __future__ import annotations

import random
from collections.abc import Iterable
from dataclasses import dataclass

RANKS = "23456789TJQKA"
SUITS = "cdhs"  # clubs, diamonds, hearts, spades

ACE = 14


@dataclass(frozen=True, slots=True)
class Card:
    """One card. ``rank`` runs from 2 to 14 (ace); ``suit`` is one of ``c d h s``."""

    rank: int
    suit: str

    def __post_init__(self) -> None:
        if not 2 <= self.rank <= ACE or self.suit not in SUITS or len(self.suit) != 1:
            raise ValueError(f"not a card: rank {self.rank!r}, suit {self.suit!r}")

    @classmethod
    def parse(cls, text: str) -> Card:
        """``Card.parse("Ah")``. Ranks are ``2-9 T J Q K A``, suits ``c d h s``."""
        if len(text) != 2 or text[0] not in RANKS or text[1] not in SUITS:
            raise ValueError(f"not a card: {text!r} (expected rank + suit, like 'Ah' or 'Td')")
        return cls(RANKS.index(text[0]) + 2, text[1])

    def __str__(self) -> str:
        return RANKS[self.rank - 2] + self.suit


def parse_cards(text: str) -> list[Card]:
    """``parse_cards("Ah Kd 7c")``: cards separated by spaces."""
    return [Card.parse(part) for part in text.split()]


def format_cards(cards: Iterable[Card]) -> str:
    return " ".join(str(card) for card in cards)


FULL_DECK: tuple[Card, ...] = tuple(Card(rank, suit) for suit in SUITS for rank in range(2, 15))


class Deck:
    """The 52 cards, shuffled by the given random stream; deals from the top.

    Pass a stream from the match seed (``ctx.rng("deck", hand_no)``), so the
    same seed always deals the same cards.
    """

    def __init__(self, rng: random.Random) -> None:
        self._cards = list(FULL_DECK)
        rng.shuffle(self._cards)

    def deal(self, count: int = 1) -> list[Card]:
        if not 0 <= count <= len(self._cards):
            raise ValueError(f"cannot deal {count} cards, {len(self._cards)} left")
        dealt, self._cards = self._cards[:count], self._cards[count:]
        return dealt

    def __len__(self) -> int:
        return len(self._cards)
