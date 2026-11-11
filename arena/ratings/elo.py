"""Multiplayer Elo.

Every match is scored as all pairwise duels between its players: finishing
ahead of someone is a win against them, sharing a rank is a draw. Each duel
uses the classic Elo expectation, and a player's change is

    delta = K / (n - 1) * sum over opponents of (score - expected)

so a match of n players moves a rating about as much as one two-player game,
however many opponents there are. Every duel adds to one side what it takes
from the other, so the deltas of a match sum to zero.

    changes = update_ratings({"ann": 1000.0}, [Placement(player="ann", rank=1), ...])
    changes["ann"].after
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from arena.engine.types import Placement

START_RATING = 1000.0
DEFAULT_K = 32.0


@dataclass(frozen=True)
class RatingChange:
    before: float
    after: float

    @property
    def delta(self) -> float:
        return self.after - self.before


def expected_score(rating: float, opponent: float) -> float:
    """Chance to beat `opponent`, counting a draw as half: 0.5 for equal ratings."""
    return 1 / (1 + 10 ** ((opponent - rating) / 400))


def update_ratings(
    ratings: Mapping[str, float], placements: Sequence[Placement], k: float = DEFAULT_K
) -> dict[str, RatingChange]:
    """New ratings for every placed player. Players missing from `ratings` start at 1000.

    Pure and deterministic: the result depends only on the arguments, not on
    their order.
    """
    players = [placement.player for placement in placements]
    if len(players) < 2:
        raise ValueError("a rated match needs at least 2 players")
    if len(set(players)) != len(players):
        raise ValueError("each player may be placed only once")
    if any(placement.rank < 1 for placement in placements):
        raise ValueError("ranks start at 1")
    if k <= 0:
        raise ValueError("k must be positive")

    before = {player: ratings.get(player, START_RATING) for player in players}
    rank = {placement.player: placement.rank for placement in placements}
    per_duel = k / (len(players) - 1)
    changes = {}
    for player in players:
        surplus = sum(
            _score(rank[player], rank[other]) - expected_score(before[player], before[other])
            for other in players
            if other != player
        )
        changes[player] = RatingChange(before[player], before[player] + per_duel * surplus)
    return changes


def overall_rating(per_game: Mapping[str, tuple[float, int]]) -> float:
    """One rating across games: the per-game ratings averaged, weighted by games played.

    `per_game` maps a game id to (rating, games played). A player who has
    played nothing is at the start rating (D-031).
    """
    if any(played < 0 for _, played in per_game.values()):
        raise ValueError("games played cannot be negative")
    total = sum(played for _, played in per_game.values())
    if total == 0:
        return START_RATING
    return sum(rating * played for rating, played in per_game.values()) / total


def _score(rank: int, other_rank: int) -> float:
    if rank < other_rank:
        return 1.0
    if rank == other_rank:
        return 0.5
    return 0.0
