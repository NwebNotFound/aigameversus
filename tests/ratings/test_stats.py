import pytest

from arena.ratings.stats import average_placement, bluff_rate, lie_rate, rate, win_rate


def test_win_rate():
    assert win_rate(3, 4) == 0.75
    assert win_rate(0, 5) == 0.0


def test_no_games_means_no_rate_yet():
    assert win_rate(0, 0) is None
    assert bluff_rate(0, 0) is None
    assert lie_rate(0, 0) is None


def test_bluff_and_lie_rates_are_shares():
    assert bluff_rate(2, 8) == 0.25
    assert lie_rate(1, 10) == 0.1


@pytest.mark.parametrize(("count", "total"), [(-1, 3), (1, -3), (4, 3)])
def test_impossible_counts_are_rejected(count: int, total: int):
    with pytest.raises(ValueError):
        rate(count, total)


def test_average_placement():
    assert average_placement([1, 2, 3, 2]) == 2.0
    assert average_placement([]) is None


def test_average_placement_rejects_rank_zero():
    with pytest.raises(ValueError, match="ranks start at 1"):
        average_placement([1, 0])
