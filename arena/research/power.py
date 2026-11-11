"""Exact power of a two-sided binomial test, for sample-size arguments.

    power(56, chance=0.25, true=0.45, alpha=0.05 / 8)
    detectable(56, chance=0.25, alpha=0.05 / 8)   # smallest true rate found with 80 % power

Matches that share a seed are not fully independent, so for a seeded design
these numbers are a guide, not a guarantee.
"""

from math import comb


def _pmf(n: int, p: float) -> list[float]:
    return [comb(n, k) * p**k * (1 - p) ** (n - k) for k in range(n + 1)]


def rejected_counts(n: int, chance: float, alpha: float) -> list[int]:
    """The win counts out of `n` at which the test rejects `chance`.

    Equal tails: a count is rejected when the probability of a count at least
    as far out on its side is at most `alpha / 2`.
    """
    if n < 1 or not 0 < chance < 1 or not 0 < alpha < 1:
        raise ValueError("need n >= 1, 0 < chance < 1 and 0 < alpha < 1")
    pmf = _pmf(n, chance)
    lower = [sum(pmf[: k + 1]) for k in range(n + 1)]
    upper = [sum(pmf[k:]) for k in range(n + 1)]
    return [k for k in range(n + 1) if min(lower[k], upper[k]) <= alpha / 2]


def power(n: int, chance: float, true: float, alpha: float) -> float:
    """Probability that `n` matches reject `chance` when the real rate is `true`."""
    if not 0 <= true <= 1:
        raise ValueError("need 0 <= true <= 1")
    pmf = _pmf(n, true)
    return sum(pmf[k] for k in rejected_counts(n, chance, alpha))


def detectable(n: int, chance: float, alpha: float, wanted: float = 0.8) -> float | None:
    """The smallest rate above `chance`, in steps of 0.01, found with power `wanted`.

    `None` if even a rate of 1 is not found that often.
    """
    for percent in range(int(chance * 100) + 1, 101):
        if power(n, chance, percent / 100, alpha) >= wanted:
            return percent / 100
    return None
