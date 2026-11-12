"""The reliability verdict: from a model's newest moves and matches on this arena."""

from arena.config import ReliabilityRules, load_config
from arena.db.reliability import verdict

RULES = ReliabilityRules()


def moves(n, match="m1", **data):
    told = {"cutoffs": 0, "rate_limits": 0}
    return [(match, {"fallback": None, **told, **data}) for _ in range(n)]


def test_the_rules_come_from_the_config_with_these_defaults():
    assert load_config().reliability == RULES
    assert (RULES.moves, RULES.matches) == (20, 2)


def test_enough_clean_moves_are_ok():
    found = verdict(moves(10) + moves(10, match="m2"), 0, RULES)

    assert (found.status, found.reason, found.n, found.matches) == ("ok", None, 20, 2)
    assert (found.fallback_share, found.cutoff_share, found.telemetry_moves) == (0.0, 0.0, 20)
    assert found.warnings == []


def test_fewer_moves_than_a_verdict_needs_are_unknown():
    found = verdict(moves(19), 0, RULES)

    assert found.status == "unknown" and "19 moves" in found.reason


def test_a_seat_that_gave_up_recently_is_unreliable_whatever_its_moves():
    found = verdict([], 1, RULES)

    assert found.status == "unreliable" and "gave up in 1 of its last 2 matches" in found.reason


def test_more_than_half_of_the_newest_moves_by_the_bot_is_unreliable():
    newest = moves(11, fallback="rejected") + moves(9)
    found = verdict(newest + moves(30), 0, RULES)  # only the newest 20 count

    assert found.status == "unreliable" and found.fallback_share == 11 / 20
    half = moves(10, fallback="rejected") + moves(10)
    assert verdict(half, 0, RULES).status == "ok"  # 50 % is not above


def test_cut_off_answers_and_rate_limits_are_warnings_not_failures():
    found = verdict(moves(5, cutoffs=1) + moves(15, rate_limits=1), 0, RULES)

    assert found.status == "ok"
    assert found.cutoff_share == 0.25 and found.rate_limits_per_move == 0.75
    assert any("cut off" in w for w in found.warnings)
    assert any("rate-limited" in w for w in found.warnings)


def test_moves_from_before_the_counters_are_not_counted_as_clean():
    old = [("m1", {"fallback": None}) for _ in range(15)]  # logs before cutoffs/rate_limits
    found = verdict(moves(5, cutoffs=1) + old, 0, RULES)

    assert found.telemetry_moves == 5
    assert found.cutoff_share == 1.0  # of the moves that tell, not of all 20
    assert any("known for 5 of 20 moves only" in w for w in found.warnings)
    none_told = verdict(old + old, 0, RULES)
    assert (none_told.cutoff_share, none_told.rate_limits_per_move) == (None, None)


def test_the_thresholds_follow_the_rules():
    strict = ReliabilityRules(moves=5, fallback_above=0.1)

    assert verdict(moves(1, fallback="timeout") + moves(4), 0, strict).status == "unreliable"


def test_refused_answers_and_how_many_of_them_were_cut_off_are_counted():
    # 13 refused answers in 20 moves, 12 of them cut off at the output limit (be2f808a, Hy3)
    hard = [("m1", {"fallback": None, "answers": 2, "cutoffs": 1, "rate_limits": 0})] * 12
    one = [("m1", {"fallback": None, "answers": 2, "cutoffs": 0, "rate_limits": 0})]
    clean = [("m1", {"fallback": None, "answers": 1, "cutoffs": 0, "rate_limits": 0})] * 7
    found = verdict(hard + one + clean, 0, RULES, last_seen="2026-11-12T01:00:00+00:00")

    assert found.rejected_cut_off == 12
    assert found.rejected_rate == 13 / 33
    assert found.last_seen == "2026-11-12T01:00:00+00:00"
    assert any("12 of 13 refused answers ran into the output limit" in w for w in found.warnings)
    assert found.status == "ok"  # every move ended valid: a warning, not a failure
