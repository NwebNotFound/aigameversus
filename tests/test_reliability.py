"""The reliability verdict: from a model's newest moves and matches on this arena."""

from arena.db.reliability import MOVES, verdict


def moves(n, **data):
    return [{"fallback": None, "cutoffs": 0, "rate_limits": 0, **data} for _ in range(n)]


def test_enough_clean_moves_are_ok():
    found = verdict(moves(MOVES), failed_recently=0)

    assert (found.status, found.reason, found.n, found.fallback_share) == ("ok", None, 20, 0.0)
    assert found.warnings == []


def test_fewer_moves_than_a_verdict_needs_are_unknown():
    found = verdict(moves(MOVES - 1), failed_recently=0)

    assert found.status == "unknown" and "19 moves" in found.reason


def test_a_seat_that_gave_up_recently_is_unreliable_whatever_its_moves():
    found = verdict([], failed_recently=1)

    assert found.status == "unreliable" and "gave up in 1 of its last 2 matches" in found.reason


def test_more_than_half_of_the_newest_moves_by_the_bot_is_unreliable():
    newest = moves(11, fallback="rejected") + moves(9)
    found = verdict(newest + moves(30), failed_recently=0)  # only the newest 20 count

    assert found.status == "unreliable" and found.fallback_share == 11 / 20
    assert (
        verdict(moves(10, fallback="rejected") + moves(10), 0).status == "ok"
    )  # 50 % is not above


def test_cut_off_answers_and_rate_limits_are_warnings_not_failures():
    found = verdict(moves(5, cutoffs=1) + moves(15, rate_limits=1), failed_recently=0)

    assert found.status == "ok"
    assert any("cut off" in w for w in found.warnings)
    assert any("rate-limited" in w for w in found.warnings)
