"""Power of the exact binomial test, checked against values that can be counted by hand."""

import pytest

from arena.research.power import detectable, power, rejected_counts


def test_rejection_region_of_a_fair_coin_in_ten_throws():
    # P(0) = P(10) = 1/1024 and P(<=1) = P(>=9) = 11/1024 = 0.0107; P(<=2) = 0.0547.
    assert rejected_counts(10, 0.5, 0.05) == [0, 1, 9, 10]
    assert rejected_counts(10, 0.5, 0.01) == [0, 10]


def test_under_the_null_the_test_rejects_no_more_often_than_alpha():
    for n, chance, alpha in [(56, 0.25, 0.05), (56, 0.25, 0.05 / 8), (96, 0.5, 0.05)]:
        assert power(n, chance, chance, alpha) <= alpha


def test_power_of_a_fair_coin_test_against_a_sure_thing():
    assert power(10, 0.5, 1.0, 0.05) == 1.0
    assert power(10, 0.5, 0.5, 0.05) == pytest.approx(22 / 1024)


def test_power_grows_with_the_gap_and_with_the_matches():
    assert power(56, 0.25, 0.35, 0.05) < power(56, 0.25, 0.45, 0.05)
    assert power(28, 0.25, 0.45, 0.05) < power(56, 0.25, 0.45, 0.05)


def test_detectable_is_the_first_rate_with_the_wanted_power():
    rate = detectable(56, 0.25, 0.05)

    assert rate is not None
    assert power(56, 0.25, rate, 0.05) >= 0.8
    assert power(56, 0.25, rate - 0.01, 0.05) < 0.8


def test_detectable_is_none_when_no_rate_is_found_often_enough():
    assert detectable(3, 0.5, 0.05) is None


def test_bad_arguments_are_refused():
    with pytest.raises(ValueError):
        rejected_counts(0, 0.5, 0.05)
    with pytest.raises(ValueError):
        rejected_counts(10, 1.0, 0.05)
    with pytest.raises(ValueError):
        power(10, 0.5, 1.5, 0.05)
