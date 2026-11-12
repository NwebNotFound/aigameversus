"""Jev design stays infeasible/unapproved until real prerequisites exist; no clients."""

from pathlib import Path

import pytest
import yaml

PLAN = Path(__file__).resolve().parents[2] / "research/JEV/PLAN.yaml"


@pytest.fixture
def plan():
    return yaml.safe_load(PLAN.read_text(encoding="utf-8"))


def test_no_real_approval_or_spend(plan):
    assert plan["implementation_mode"] == "fake_only"
    assert plan["real_call_approvals"] == []
    assert plan["budget"]["approved_real_eur"] == 0
    assert plan["budget"]["automatic_retries"] == 0
    assert plan["budget"]["proposed_real_eur"] <= plan["budget"]["per_job_ceiling_eur"]


def test_inventory_humans_and_registration_are_blocking(plan):
    gates = plan["blocking_preconditions"]
    assert gates["humans_available"] is False
    assert set(gates["human_raters"]) == {"rater_a", "rater_b", "adjudicator"}
    assert all(person is None for person in gates["human_raters"].values())
    assert gates["eligible_inventory_verified"] is False
    assert gates["eligible_independent_blocks"] is None
    assert gates["minimum_independent_blocks_before_any_run"] == 100
    assert gates["below_minimum_action"] == "do_not_run_spend_zero"
    registration = plan["registration"]
    assert registration["state"] == "design_frozen_manifest_pending"
    assert registration["merge_commit"] == "4dc0baf5abebf7ec61ac0993ef9b8680f7ea6797"
    assert all(
        registration[field] is None
        for field in ("corpus_manifest_hash", "split_hash", "configuration_hash")
    )


def test_case_and_call_budgets_do_not_silently_grow(plan):
    repair, referee = plan["repair"], plan["referee"]
    assert repair["development_target"] + repair["validation_target"] == repair["target_cases"]
    assert 100 <= repair["target_cases"] <= 200
    assert plan["budget"]["max_real_requests_if_separately_approved"] == (
        repair["target_cases"] + referee["target_matches"]
    )
    assert repair["threshold_statistic"] == "maximum_returned_option_probability"
    assert repair["free_text_repair"] == "forbidden"
    assert repair["strategic_recommendation_or_missing_amount_guess"] == "forbidden"


def test_precision_gate_needs_59_perfect_independent_accepts_and_enough_coverage(plan):
    # Exact one-sided lower bound with zero errors, alpha=.05.
    assert pytest.approx(0.8608916593) == 0.05 ** (1 / 20)
    assert 0.05 ** (1 / 58) < 0.95 <= 0.05 ** (1 / 59)
    assert plan["repair"]["minimum_error_free_accepted_for_precision_gate"] == 59
    assert 59 / plan["repair"]["validation_target"] == pytest.approx(
        plan["repair"]["necessary_holdout_acceptance_coverage"], abs=1e-6
    )
    # The 100-case pilot leaves only 40 holdout cases and cannot reach this gate.
    assert 100 - plan["repair"]["development_target"] < 59


def test_concentration_is_not_an_option_count_independent_probability():
    p_top = 0.90
    confidence_2 = (p_top - 1 / 2) / (1 - 1 / 2)
    confidence_10 = (p_top - 1 / 10) / (1 - 1 / 10)
    assert confidence_2 == pytest.approx(0.8)
    assert confidence_10 == pytest.approx(0.8888888889)
