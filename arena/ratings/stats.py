"""Statistics that are plain arithmetic on counts. ``None`` means "no data yet", not 0."""

from collections.abc import Sequence


def rate(count: int, total: int) -> float | None:
    """`count` out of `total` as a share from 0 to 1."""
    if count < 0 or total < 0:
        raise ValueError("counts cannot be negative")
    if count > total:
        raise ValueError(f"count {count} is larger than total {total}")
    return None if total == 0 else count / total


def win_rate(wins: int, games: int) -> float | None:
    return rate(wins, games)


def bluff_rate(bluffs: int, plays: int) -> float | None:
    """Share of plays that were bluffs, e.g. a false claim in Liar's Deck."""
    return rate(bluffs, plays)


def lie_rate(lies: int, statements: int) -> float | None:
    """Share of public statements flagged as contradicting the speaker's own thoughts."""
    return rate(lies, statements)


def average_placement(ranks: Sequence[int]) -> float | None:
    """Mean finishing rank (1 = winner)."""
    if any(rank < 1 for rank in ranks):
        raise ValueError("ranks start at 1")
    return None if not ranks else sum(ranks) / len(ranks)
