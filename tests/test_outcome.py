"""The one-line outcome of a match row: from the record alone, no result for a running match."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from arena.api.outcome import outcome_of
from arena.db.match_store import MatchRecord, Seat
from arena.engine.types import Placement

NOW = datetime(2026, 11, 12, tzinfo=UTC)


def record(status="finished", players=("p1", "p2", "p3"), ranks=(1, 2, 3), seats=None):
    return MatchRecord(
        id=uuid4(),
        game="poker",
        status=status,
        players=list(players),
        seed=1,
        settings={},
        started_at=NOW,
        finished_at=None if status == "running" else NOW,
        placements=None
        if status == "running"
        else [Placement(player=p, rank=r) for p, r in zip(players, ranks, strict=False)],
        seats=seats,
    )


def models(*names):
    return {f"p{i}": Seat(name=n, model_id=n, kind="model") for i, n in enumerate(names, 1)}


def test_a_single_winner_is_named_by_the_display_name_in_both_languages():
    out = outcome_of(record(seats=models("gpt-luna", "glm-flash", "mimo")))

    assert (out.kind, out.winners) == ("won", ["p1"])
    assert out.text == {"en": "gpt-luna won", "de": "gpt-luna gewann"}


def test_bots_are_named_by_seat_number_and_old_records_without_seats_read_as_bots():
    assert outcome_of(record(ranks=(2, 1, 3))).text["en"] == "Bot 2 won"


def test_two_or_three_winners_are_listed_and_many_are_counted():
    two = outcome_of(record(ranks=(1, 1, 3), seats=models("a", "b", "c")))
    many = outcome_of(record(players=("p1", "p2", "p3", "p4", "p5"), ranks=(1, 1, 1, 1, 5)))

    assert two.text == {"en": "a and b won", "de": "a und b gewannen"}
    assert many.text == {"en": "4 of 5 players won", "de": "4 von 5 Spielern gewannen"}


def test_a_running_match_shows_no_result_and_a_stopped_one_says_so():
    running = outcome_of(record("running"))
    stopped = outcome_of(record("interrupted"))

    assert (running.kind, running.winners, running.text["en"]) == ("running", [], "In progress")
    assert stopped.kind == "stopped" and "Interrupted" in stopped.text["en"]
    assert outcome_of(record("failed")).text["de"] == "Fehlgeschlagen"


def test_a_finished_match_without_placements_just_says_finished():
    bare = record()
    bare.placements = None

    assert outcome_of(bare).text["en"] == "Finished" and outcome_of(bare).winners == []


@pytest.mark.parametrize("status", ["running", "failed", "interrupted", "aborted"])
def test_only_a_finished_match_has_winners(status):
    assert outcome_of(record(status)).winners == []
