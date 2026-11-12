"""Cross-match insights per model: how often it wins, where it places, against whom, at what cost.

Every number rests on rated matches (`match_placements`) and carries its count. Intervals
come from resampling whole matches (docs/METRICS.md): a match is drawn with all its seats,
so two seats of one model in one match never count as two independent results. The
resampling is seeded, so the same data always gives the same intervals. Fewer than
`MIN_MATCHES` matches make a number provisional: shown, not ranked.
"""

from __future__ import annotations

import math
import random
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from itertools import combinations
from statistics import fmean
from typing import Any
from uuid import UUID

MIN_MATCHES = 10  # below this a model's numbers are provisional (docs/METRICS.md)
RESAMPLES = 2000
LEVEL = 0.95
SEED = "insights/1"
VERSION = "insights/1"


@dataclass(frozen=True)
class Seat:
    """One placed seat of a rated match."""

    match_id: UUID
    game: str
    model: str
    name: str
    rank: int
    players: int


def score(rank: int, players: int) -> float:
    """1 for first place, 0 for last, evenly between: places compare across table sizes."""
    return (players - rank) / (players - 1) if players > 1 else 0.0


def interval(values: Sequence[float], key: str) -> tuple[float, float] | tuple[None, None]:
    """The central LEVEL interval of the mean of `values`, one value per match, by resampling
    whole matches RESAMPLES times; (None, None) without a value. `key` seeds the draws."""
    if not values:
        return None, None
    if len(values) == 1:
        return values[0], values[0]
    rng = random.Random(f"{SEED}/{key}")
    n = len(values)
    means = sorted(fmean(rng.choices(values, k=n)) for _ in range(RESAMPLES))
    tail = (1 - LEVEL) / 2
    low = means[int(math.floor(tail * (RESAMPLES - 1)))]
    high = means[int(math.ceil((1 - tail) * (RESAMPLES - 1)))]
    return low, high


def wilson(successes: int, trials: int, z: float = 1.959964) -> tuple[float, float] | None:
    """The Wilson score interval of a share; None without a trial."""
    if trials == 0:
        return None
    p = successes / trials
    centre = (p + z * z / (2 * trials)) / (1 + z * z / trials)
    half = (
        z * math.sqrt(p * (1 - p) / trials + z * z / (4 * trials * trials)) / (1 + z * z / trials)
    )
    return max(0.0, centre - half), min(1.0, centre + half)


def _rounded(value: float | None) -> float | None:
    return None if value is None else round(value, 4)


def _estimate(values: list[float], key: str) -> dict[str, Any]:
    low, high = interval(values, key)
    return {
        "value": _rounded(fmean(values)) if values else None,
        "low": _rounded(low),
        "high": _rounded(high),
        "n": len(values),
    }


def by_match(seats: Iterable[Seat]) -> dict[UUID, list[Seat]]:
    matches: dict[UUID, list[Seat]] = defaultdict(list)
    for seat in seats:
        matches[seat.match_id].append(seat)
    return matches


def per_model(seats: Sequence[Seat]) -> list[dict[str, Any]]:
    """Per model: matches, wins, win rate and placement score with resampled intervals.

    A model in several seats of one match gets that match's mean of them: one value per
    match, as the resampling draws matches.
    """
    wins: dict[str, list[float]] = defaultdict(list)
    places: dict[str, list[float]] = defaultdict(list)
    names: dict[str, str] = {}
    for match_seats in by_match(seats).values():
        mine: dict[str, list[Seat]] = defaultdict(list)
        for seat in match_seats:
            mine[seat.model].append(seat)
            names.setdefault(seat.model, seat.name)
        for model, own in mine.items():
            wins[model].append(fmean(1.0 if s.rank == 1 else 0.0 for s in own))
            places[model].append(fmean(score(s.rank, s.players) for s in own))
    out = []
    for model in sorted(wins):
        matches = len(wins[model])
        out.append(
            {
                "model_id": model,
                "name": names[model],
                "matches": matches,
                "wins": round(sum(wins[model]), 4),
                "provisional": matches < MIN_MATCHES,
                "win_rate": _estimate(wins[model], f"win/{model}"),
                "placement_score": _estimate(places[model], f"place/{model}"),
            }
        )
    return out


def head_to_head(seats: Sequence[Seat]) -> list[dict[str, Any]]:
    """Every pair of models that met: in how many matches each placed above the other.

    One result per match: the model with the better mean rank of its seats there is above;
    equal means are a tie. `a_share` is the share of the decided matches that `a` won, with
    its Wilson interval.
    """
    tally: dict[tuple[str, str], list[int]] = defaultdict(lambda: [0, 0, 0])  # a, b, ties
    for match_seats in by_match(seats).values():
        ranks: dict[str, list[int]] = defaultdict(list)
        for seat in match_seats:
            ranks[seat.model].append(seat.rank)
        mean = {model: fmean(r) for model, r in ranks.items()}
        for a, b in combinations(sorted(mean), 2):
            counts = tally[(a, b)]
            if mean[a] < mean[b]:
                counts[0] += 1
            elif mean[b] < mean[a]:
                counts[1] += 1
            else:
                counts[2] += 1
    out = []
    for (a, b), (above, below, ties) in sorted(tally.items()):
        decided = above + below
        bounds = wilson(above, decided)
        out.append(
            {
                "a": a,
                "b": b,
                "matches": above + below + ties,
                "a_above": above,
                "b_above": below,
                "ties": ties,
                "a_share": {
                    "value": _rounded(above / decided) if decided else None,
                    "low": _rounded(bounds[0]) if bounds else None,
                    "high": _rounded(bounds[1]) if bounds else None,
                    "n": above,
                    "of": decided,
                },
                "provisional": above + below + ties < MIN_MATCHES,
            }
        )
    return out
