"""The reliability verdict: from a model's newest moves and matches on this arena."""

from datetime import UTC, datetime

from arena.config import ReliabilityRules, load_config
from arena.db.reliability import verdict

RULES = ReliabilityRules()


def moves(n, match="m1", **data):
    told = {"cutoffs": 0, "rate_limits": 0, "answers": 1}
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


def test_the_share_of_refused_answers_counts_all_answers_of_the_moves():
    # 10 moves took their 2nd answer (1 refused each), 10 took their 1st
    found = verdict(moves(10, answers=2) + moves(10), 0, RULES)

    assert (found.answers, found.rejected, found.rejected_rate) == (30, 10, 10 / 30)


def test_a_move_the_bot_played_has_all_its_answers_refused():
    found = verdict(moves(1, answers=3, fallback="rejected") + moves(19), 0, RULES)

    assert (found.answers, found.rejected) == (22, 3)


def test_twelve_of_thirteen_refused_answers_cut_off_is_named_in_a_warning():
    """The match be2f808a case: 13 refused answers, 12 of them ran into the output limit."""
    cut_moves = moves(12, answers=2, cutoffs=1) + moves(1, answers=2, cutoffs=0) + moves(7)
    found = verdict(cut_moves, 0, RULES)

    assert found.status == "ok"
    assert (found.rejected, found.rejected_told, found.rejected_cut_off) == (13, 13, 12)
    assert any("12 of 13 refused answers ran into the output limit" in w for w in found.warnings)


def test_few_refusals_or_few_cut_offs_give_no_dominance_warning():
    few = verdict(moves(2, answers=2, cutoffs=1) + moves(18), 0, RULES)  # only 2 refused
    mixed = verdict(moves(3, answers=2, cutoffs=1) + moves(3, answers=2) + moves(14), 0, RULES)

    assert not any("refused answers ran into" in w for w in few.warnings)
    assert not any("refused answers ran into" in w for w in mixed.warnings)  # 3 of 6 is not above


def test_a_cut_off_answer_that_still_made_a_move_is_not_a_refused_one():
    found = verdict(moves(20, answers=1, cutoffs=1), 0, RULES)

    assert (found.rejected, found.rejected_cut_off) == (0, 0)


def test_logs_without_telemetry_say_unknown_not_zero():
    old = [("m1", {"fallback": None, "answers": 2}) for _ in range(20)]  # before cutoffs existed
    found = verdict(old, 0, RULES)

    assert found.rejected == 20 and found.rejected_rate == 20 / 40
    assert found.rejected_cut_off is None and found.rejected_told == 0
    bare = verdict([("m1", {"fallback": None}) for _ in range(20)], 0, RULES)
    assert (bare.answers, bare.rejected_rate) == (0, None)


def test_last_seen_is_what_the_caller_knows_of_the_newest_move():
    seen = datetime(2026, 11, 12, 9, 30, tzinfo=UTC)

    assert verdict(moves(20), 0, RULES, seen).last_seen == seen
    assert verdict(moves(20), 0, RULES).last_seen is None


def test_the_dominance_thresholds_follow_the_rules():
    lax = ReliabilityRules(cut_off_dominates_above=0.95)
    two_thirds = moves(8, answers=2, cutoffs=1) + moves(4, answers=2) + moves(8)

    assert any("8 of 12 refused" in w for w in verdict(two_thirds, 0, RULES).warnings)
    assert not any("refused answers ran into" in w for w in verdict(two_thirds, 0, lax).warnings)
