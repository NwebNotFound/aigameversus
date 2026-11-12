import pytest

from arena.research.werewolf_pilot import outcomes, paired_reliability, rates, reliability


def event(kind, player="p1", **data):
    return {"type": kind, "data": {"player": player, **data}}


def cell(seating=1, model="llama-scout", events=()):
    return {
        "seed": 42,
        "seating": seating,
        "seats": {"p1": model},
        "events": list(events),
        "record": {"id": f"m{seating}"},
    }


def test_retries_and_fallback_have_distinct_denominators():
    events = [
        event("action_rejected", error="Your text has 50 words; say it in at most 40."),
        event("action_rejected", error="cut off at the length limit"),
        event("action_fallback", reason="timeout"),
        event("action_accepted"),
    ]
    row = rates(reliability(events, {"p1": "a"})["a"])
    assert row["turns"] == 2 and row["rejected_answers"] == 2
    assert row["fallback_share"] == 0.5 and row["word_limit_rejections_per_decision"] == 0.5
    assert rates({})["fallback_share"] is None


def test_pairing_rejects_changed_roster_and_does_not_use_unpaired_cells():
    baseline = [cell(1, events=[event("action_fallback", reason="invalid")]), cell(2)]
    paired = paired_reliability(baseline, [cell(1, events=[event("action_accepted")])])
    assert len(paired["pairs"]) == 1 and paired["missing_baseline_cells"] == 1
    assert paired["pooled_paired_llama"]["P1"]["fallback_share"] == 1
    assert paired["pooled_paired_llama"]["P3"]["fallback_share"] == 0
    with pytest.raises(ValueError, match="no identical"):
        paired_reliability(baseline, [cell(1, model="replacement")])


def test_bot_votes_do_not_become_model_vote_accuracy():
    row = {
        "seats": {"p1": "a", "p2": "b"},
        "record": {"placements": [{"player": "p1", "rank": 1}, {"player": "p2", "rank": 2}]},
        "events": [
            event("role_assigned", role="villager"),
            event("role_assigned", "p2", role="werewolf"),
            event("action_fallback"),
            event("vote_cast", target="p2"),
            event("action_accepted"),
            event("vote_cast", target="p2"),
        ],
    }
    team, roles, votes = outcomes(row)
    assert team == "village" and sum(r["won"] for r in roles) == 1
    assert votes["model_village_votes"] == votes["bot_village_votes"] == 1
    assert votes["model_votes_on_wolf"] == votes["bot_votes_on_wolf"] == 1
