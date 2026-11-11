import random

import pytest

from arena.engine.types import Placement
from arena.ratings.elo import (
    START_RATING,
    expected_score,
    overall_rating,
    update_ratings,
)


def places(*ranked: tuple[str, int]) -> list[Placement]:
    return [Placement(player=player, rank=rank) for player, rank in ranked]


def deltas(changes) -> dict[str, float]:
    return {player: change.delta for player, change in changes.items()}


# --- the classic two-player formula -----------------------------------------


def test_equal_players_expect_half():
    assert expected_score(1000, 1000) == 0.5


def test_400_points_stronger_expects_ten_to_one():
    assert expected_score(1400, 1000) == pytest.approx(10 / 11)


def test_equal_players_winner_gains_half_of_k():
    changes = update_ratings({}, places(("ann", 1), ("bob", 2)))

    assert changes["ann"].before == START_RATING
    assert deltas(changes) == {"ann": pytest.approx(16), "bob": pytest.approx(-16)}


def test_favourite_win_and_upset_textbook_values():
    ratings = {"strong": 1200.0, "weak": 1000.0}
    # E(strong) = 1 / (1 + 10^(-200/400)) = 0.7597
    favourite = update_ratings(ratings, places(("strong", 1), ("weak", 2)))
    upset = update_ratings(ratings, places(("weak", 1), ("strong", 2)))

    assert favourite["strong"].delta == pytest.approx(32 * (1 - 0.759746), abs=1e-4)
    assert upset["weak"].delta == pytest.approx(32 * 0.759746, abs=1e-4)
    assert upset["weak"].after == pytest.approx(1024.31, abs=0.01)


def test_draw_between_equals_changes_nothing():
    changes = update_ratings({}, places(("ann", 1), ("bob", 1)))

    assert deltas(changes) == {"ann": 0.0, "bob": 0.0}


def test_draw_moves_the_ratings_towards_each_other():
    changes = update_ratings({"strong": 1200.0, "weak": 1000.0}, places(("strong", 1), ("weak", 1)))

    assert changes["strong"].delta < 0 < changes["weak"].delta
    assert changes["weak"].delta == pytest.approx(32 * (0.5 - 0.240254), abs=1e-4)


def test_k_factor_is_configurable():
    changes = update_ratings({}, places(("ann", 1), ("bob", 2)), k=16)

    assert changes["ann"].delta == pytest.approx(8)


# --- more players ------------------------------------------------------------


def test_four_equal_players_spread_evenly():
    # K / 3 per duel: winner 3 wins, second 2 wins 1 loss, ...
    changes = update_ratings({}, places(("a", 1), ("b", 2), ("c", 3), ("d", 4)))

    assert deltas(changes) == {
        "a": pytest.approx(16),
        "b": pytest.approx(16 / 3),
        "c": pytest.approx(-16 / 3),
        "d": pytest.approx(-16),
    }


def test_shared_rank_counts_as_a_draw_between_them():
    changes = update_ratings({}, places(("a", 1), ("b", 1), ("c", 3)))

    # per duel K/2 = 16: a and b draw each other (0) and beat c (+0.5 each).
    assert deltas(changes) == {
        "a": pytest.approx(8),
        "b": pytest.approx(8),
        "c": pytest.approx(-16),
    }


def test_winner_of_a_big_table_moves_like_one_duel():
    """Normalising by opponents keeps a 6-player win at the size of a 2-player win."""
    six = update_ratings({}, places(*[(f"p{i}", i) for i in range(1, 7)]))

    assert six["p1"].delta == pytest.approx(16)
    assert six["p6"].delta == pytest.approx(-16)


@pytest.mark.parametrize("players", [2, 3, 4, 5, 6])
def test_deltas_sum_to_zero_for_any_table(players: int):
    rng = random.Random(players)
    for _ in range(200):
        names = [f"p{i}" for i in range(players)]
        ratings = {name: rng.uniform(600, 1600) for name in names}
        ranks = [rng.randint(1, players) for _ in names]

        changes = update_ratings(ratings, places(*zip(names, ranks, strict=True)))

        assert sum(deltas(changes).values()) == pytest.approx(0, abs=1e-9)
        assert all(abs(change.delta) <= 32 for change in changes.values())


def test_beating_stronger_opponents_earns_more():
    weak_field = update_ratings(
        {"me": 1000.0, "x": 800.0, "y": 800.0}, places(("me", 1), ("x", 2), ("y", 3))
    )
    strong_field = update_ratings(
        {"me": 1000.0, "x": 1200.0, "y": 1200.0}, places(("me", 1), ("x", 2), ("y", 3))
    )

    assert strong_field["me"].delta > weak_field["me"].delta > 0


def test_result_does_not_depend_on_input_order():
    ratings = {"a": 1100.0, "b": 950.0, "c": 1010.0}
    forward = update_ratings(ratings, places(("a", 2), ("b", 1), ("c", 3)))
    backward = update_ratings(ratings, places(("c", 3), ("b", 1), ("a", 2)))

    assert forward == backward


def test_players_without_a_rating_start_at_1000():
    changes = update_ratings({"ann": 1100.0}, places(("ann", 1), ("new", 2)))

    assert changes["new"].before == START_RATING


@pytest.mark.parametrize(
    ("placements", "message"),
    [
        (places(("ann", 1)), "at least 2 players"),
        (places(("ann", 1), ("ann", 2)), "only once"),
        (places(("ann", 0), ("bob", 1)), "ranks start at 1"),
    ],
)
def test_bad_placements_are_rejected(placements, message):
    with pytest.raises(ValueError, match=message):
        update_ratings({}, placements)


def test_k_must_be_positive():
    with pytest.raises(ValueError, match="positive"):
        update_ratings({}, places(("a", 1), ("b", 2)), k=0)


# --- overall rating ----------------------------------------------------------


def test_overall_is_the_mean_weighted_by_games_played():
    assert overall_rating({"poker": (1100.0, 3), "werewolf": (1000.0, 1)}) == pytest.approx(1075)


def test_overall_without_games_is_the_start_rating():
    assert overall_rating({}) == START_RATING
    assert overall_rating({"poker": (1100.0, 0)}) == START_RATING


def test_overall_rejects_negative_game_counts():
    with pytest.raises(ValueError, match="negative"):
        overall_rating({"poker": (1100.0, -1)})
