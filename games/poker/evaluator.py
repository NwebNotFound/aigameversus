"""Hold'em hand evaluation: best five cards, comparison, winners and win chances.

    best_hand(parse_cards("Ah Kh Qh Jh Th 2c 3d")).category  # HandCategory.ROYAL_FLUSH
    winners({"ann": ann_cards, "bob": bob_cards}, board)      # ["ann"], or both on a tie

Results order the way poker does: a higher category wins, and inside a category
``tiebreak`` decides, rank by rank. Suits never break a tie.
"""

from __future__ import annotations

import itertools
import math
import random
from collections import Counter
from collections.abc import Hashable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import IntEnum

from games.poker.cards import ACE, FULL_DECK, Card

BOARD_SIZE = 5


class HandCategory(IntEnum):
    HIGH_CARD = 0
    ONE_PAIR = 1
    TWO_PAIR = 2
    THREE_OF_A_KIND = 3
    STRAIGHT = 4
    FLUSH = 5
    FULL_HOUSE = 6
    FOUR_OF_A_KIND = 7
    STRAIGHT_FLUSH = 8
    ROYAL_FLUSH = 9


@dataclass(frozen=True, order=True)
class HandValue:
    """How strong a hand is. Compare two values with ``<``, ``==``, ``max``.

    ``tiebreak`` lists the ranks that decide inside the category, most
    important first: for a full house (trips, pair), for two pair (high pair,
    low pair, kicker), for a straight its top card (5 for the wheel A-2-3-4-5).
    ``cards`` are the five cards that make the hand; they take no part in
    comparisons.
    """

    category: HandCategory
    tiebreak: tuple[int, ...]
    cards: tuple[Card, ...] = field(compare=False)


def best_hand(cards: Sequence[Card]) -> HandValue:
    """The best five-card hand out of 5 to 7 distinct cards."""
    if not 5 <= len(cards) <= 7:
        raise ValueError(f"need 5 to 7 cards, got {len(cards)}")
    if len(set(cards)) != len(cards):
        raise ValueError("the same card appears twice")

    by_rank = sorted(cards, key=lambda card: (-card.rank, card.suit))
    suit_counts = Counter(card.suit for card in cards)
    flush_suit, flush_count = suit_counts.most_common(1)[0]
    if flush_count >= 5:
        suited = [card for card in by_rank if card.suit == flush_suit]
        high = _straight_high({card.rank for card in suited})
        if high is not None:
            category = HandCategory.ROYAL_FLUSH if high == ACE else HandCategory.STRAIGHT_FLUSH
            return HandValue(category, (high,), _take(suited, _straight_ranks(high)))

    # Ranks grouped by how often they occur, each group highest first.
    counts = Counter(card.rank for card in cards)
    quads = sorted((r for r, n in counts.items() if n == 4), reverse=True)
    trips = sorted((r for r, n in counts.items() if n == 3), reverse=True)
    pairs = sorted((r for r, n in counts.items() if n == 2), reverse=True)

    if quads:
        kicker = max(r for r in counts if r != quads[0])
        return _value(HandCategory.FOUR_OF_A_KIND, by_rank, [quads[0]] * 4 + [kicker])
    if trips and (len(trips) > 1 or pairs):
        pair = max(trips[1:] + pairs)
        return _value(HandCategory.FULL_HOUSE, by_rank, [trips[0]] * 3 + [pair] * 2)
    if flush_count >= 5:
        suited = [card for card in by_rank if card.suit == flush_suit][:5]
        return HandValue(HandCategory.FLUSH, tuple(c.rank for c in suited), tuple(suited))
    high = _straight_high(set(counts))
    if high is not None:
        return HandValue(HandCategory.STRAIGHT, (high,), _take(by_rank, _straight_ranks(high)))
    if trips:
        kickers = [r for r in _distinct(by_rank) if r != trips[0]][:2]
        return _value(HandCategory.THREE_OF_A_KIND, by_rank, [trips[0]] * 3 + kickers)
    if len(pairs) >= 2:
        high_pair, low_pair = pairs[:2]
        kicker = next(r for r in _distinct(by_rank) if r not in (high_pair, low_pair))
        ranks = [high_pair] * 2 + [low_pair] * 2 + [kicker]
        return _value(HandCategory.TWO_PAIR, by_rank, ranks)
    if pairs:
        kickers = [r for r in _distinct(by_rank) if r != pairs[0]][:3]
        return _value(HandCategory.ONE_PAIR, by_rank, [pairs[0]] * 2 + kickers)
    return _value(HandCategory.HIGH_CARD, by_rank, _distinct(by_rank)[:5])


def winners[P: Hashable](holes: Mapping[P, Sequence[Card]], board: Sequence[Card]) -> list[P]:
    """The players whose hole cards plus the board make the best hand; several on a tie.

    Keeps the order of ``holes``. The board must be complete (5 cards).
    """
    if len(board) != BOARD_SIZE:
        raise ValueError(f"the board needs {BOARD_SIZE} cards for a showdown, got {len(board)}")
    if not holes:
        raise ValueError("no players")
    _check_distinct(holes, board)
    values = {player: best_hand([*hole, *board]) for player, hole in holes.items()}
    top = max(values.values())
    return [player for player, value in values.items() if value == top]


def win_probabilities[P: Hashable](
    holes: Mapping[P, Sequence[Card]],
    board: Sequence[Card],
    rng: random.Random,
    samples: int = 2000,
) -> dict[P, float]:
    """Each player's share of the pot if the hand were played to the river now.

    Missing board cards are drawn from the unseen cards; a tie splits a run
    evenly. When the remaining boards are no more than ``samples``, all of them
    are counted and the result is exact; otherwise ``samples`` random boards
    are drawn from ``rng``. The shares add up to 1.
    """
    if len(board) > BOARD_SIZE:
        raise ValueError(f"a board has at most {BOARD_SIZE} cards, got {len(board)}")
    if samples < 1:
        raise ValueError("samples must be at least 1")
    _check_distinct(holes, board)
    seen = {card for hole in holes.values() for card in hole} | set(board)
    unseen = [card for card in FULL_DECK if card not in seen]
    missing = BOARD_SIZE - len(board)

    if math.comb(len(unseen), missing) <= samples:
        runouts = list(itertools.combinations(unseen, missing))
    else:
        runouts = [rng.sample(unseen, missing) for _ in range(samples)]

    shares = dict.fromkeys(holes, 0.0)
    for runout in runouts:
        best = winners(holes, [*board, *runout])
        for player in best:
            shares[player] += 1 / len(best)
    return {player: share / len(runouts) for player, share in shares.items()}


def _straight_high(ranks: set[int]) -> int | None:
    """Top card of the highest straight in ``ranks``, or None. The ace also counts as 1."""
    if ACE in ranks:
        ranks = ranks | {1}
    for high in range(ACE, 4, -1):
        if all(rank in ranks for rank in range(high - 4, high + 1)):
            return high
    return None


def _straight_ranks(high: int) -> list[int]:
    return [ACE if rank == 1 else rank for rank in range(high, high - 5, -1)]


def _distinct(by_rank: list[Card]) -> list[int]:
    return list(dict.fromkeys(card.rank for card in by_rank))


def _value(category: HandCategory, by_rank: list[Card], ranks: list[int]) -> HandValue:
    return HandValue(category, tuple(dict.fromkeys(ranks)), _take(by_rank, ranks))


def _take(cards: list[Card], ranks: list[int]) -> tuple[Card, ...]:
    """Pick one card per entry of ``ranks``, in that order, without reusing a card."""
    pool = list(cards)
    picked = []
    for rank in ranks:
        card = next(card for card in pool if card.rank == rank)
        pool.remove(card)
        picked.append(card)
    return tuple(picked)


def _check_distinct(holes: Mapping[Hashable, Sequence[Card]], board: Sequence[Card]) -> None:
    every = [card for hole in holes.values() for card in hole] + list(board)
    if len(set(every)) != len(every):
        raise ValueError("the same card appears twice")
