"""Cross-match insights: win rate and placement with whole-match intervals, head-to-head."""

from uuid import uuid4

import pytest

from arena.ratings.insights import (
    MIN_MATCHES,
    Seat,
    head_to_head,
    interval,
    per_model,
    score,
    wilson,
)


def match(*ranks_by_model: tuple[str, int]) -> list[Seat]:
    """One rated match: (model, rank) per seat."""
    match_id = uuid4()
    players = len(ranks_by_model)
    return [Seat(match_id, "poker", m, m.upper(), rank, players) for m, rank in ranks_by_model]


def table(matches: list[list[Seat]]) -> list[Seat]:
    return [seat for m in matches for seat in m]


def test_a_placement_scores_one_for_first_and_zero_for_last_at_any_table_size():
    assert [score(r, 4) for r in (1, 2, 3, 4)] == [
        1.0,
        pytest.approx(2 / 3),
        pytest.approx(1 / 3),
        0.0,
    ]
    assert score(1, 2) == 1.0 and score(2, 2) == 0.0


def test_win_rate_and_placement_count_one_value_per_match_with_an_interval():
    seats = table(
        [match(("a", 1), ("b", 2)) for _ in range(6)]
        + [match(("a", 2), ("b", 1)) for _ in range(4)]
    )

    a, b = per_model(seats)

    assert (a["model_id"], a["matches"], a["wins"]) == ("a", 10, 6)
    assert a["win_rate"]["value"] == 0.6 and a["win_rate"]["n"] == 10
    assert a["win_rate"]["low"] < 0.6 < a["win_rate"]["high"]
    assert b["win_rate"]["value"] == 0.4 and not a["provisional"]
    assert a["placement_score"]["value"] == 0.6  # two seats: first scores 1, second 0


def test_two_seats_of_one_model_in_a_match_count_as_that_match_once():
    seats = match(("a", 1), ("a", 3), ("b", 2))

    (a, b) = per_model(seats)

    assert a["matches"] == 1 and a["wins"] == 0.5  # one of its two seats won
    assert a["placement_score"]["value"] == 0.5  # mean of 1.0 and 0.0
    assert b["matches"] == 1


def test_few_matches_are_provisional_and_one_match_has_no_spread():
    (a, b) = per_model(match(("a", 1), ("b", 2)))

    assert a["provisional"] and a["matches"] < MIN_MATCHES
    assert a["win_rate"]["low"] == a["win_rate"]["high"] == 1.0


def test_the_resampled_interval_is_the_same_every_time_and_narrows_with_more_matches():
    few = [1.0, 0.0] * 5
    many = [1.0, 0.0] * 50

    uneven = [round(i * 0.137 % 1, 3) for i in range(1, 13)]
    assert interval(uneven, "x") == interval(uneven, "x")  # seeded: the same data, the same
    low_few, high_few = interval(few, "x")
    low_many, high_many = interval(many, "x")
    assert high_many - low_many < high_few - low_few
    assert interval([], "x") == (None, None)


def test_head_to_head_gives_one_result_per_match_and_a_wilson_interval():
    seats = table(
        [match(("a", 1), ("b", 2), ("c", 3)) for _ in range(3)]
        + [match(("a", 2), ("b", 1)) for _ in range(1)]
        + [match(("a", 1), ("a", 4), ("b", 2), ("b", 3))]  # mean ranks 2.5 and 2.5: a tie
    )

    pairs = {(p["a"], p["b"]): p for p in head_to_head(seats)}

    ab = pairs[("a", "b")]
    assert (ab["matches"], ab["a_above"], ab["b_above"], ab["ties"]) == (5, 3, 1, 1)
    assert ab["a_share"]["value"] == 0.75 and ab["a_share"]["of"] == 4
    assert 0 <= ab["a_share"]["low"] < 0.75 < ab["a_share"]["high"] <= 1
    assert pairs[("a", "c")]["a_above"] == 3 and pairs[("b", "c")]["b_above"] == 0
    assert all(p["provisional"] for p in pairs.values())


def test_wilson_stays_inside_zero_and_one_and_has_no_interval_without_a_trial():
    assert wilson(0, 0) is None
    low, high = wilson(10, 10)
    assert 0.6 < low < 1 and high == pytest.approx(1.0)
    low, high = wilson(0, 10)
    assert low == 0.0 and high < 0.4
