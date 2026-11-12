"""C1 custom proposal stays outside executable experiment discovery."""

import csv
from pathlib import Path

import yaml


def test_c1_design_is_unapproved_and_keeps_factors_separate():
    root = Path(__file__).resolve().parents[2]
    plan = yaml.safe_load((root / "research/C1/PLAN.yaml").read_text())
    assert plan["schema"] == "civ_design_only_v1"
    assert not plan["execution_approved"]
    assert plan["approved_budget_eur"] == 1.00
    assert plan["execution_plan_approved"] is False
    assert plan["execution_approval_evidence"] is None
    assert plan["settings"]["prompt_version"] == "civ-p1.1"
    assert plan["settings"]["match_budget_eur"] == 0.20
    assert plan["requested_preset"]["round_limit_api_setting"] == "rounds"
    assert plan["requested_preset"]["rounds"] == 20
    assert len(plan["models"]) == 4
    assert plan["baseline"]["expected_base_calls_upper"] == 80
    assert plan["baseline"]["strategy_text"] == "off"
    assert plan["baseline"]["private_plan"] == "off"
    assert plan["later_factorial"]["prompt_version"] == "civ-p1.1"
    assert plan["later_factorial"]["total_cells_including_baseline"] == 16
    assert not (root / "experiments/C1_civ_pilot.yaml").exists()


def test_c1_explicit_csv_is_exactly_four_cyclic_tables():
    root = Path(__file__).resolve().parents[2]
    plan = yaml.safe_load((root / "research/C1/PLAN.yaml").read_text())
    with (root / "research/C1" / plan["schedule"]).open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == plan["max_matches"] == 4
    for index, row in enumerate(rows):
        assert int(row["order"]) == index + 1
        assert int(row["seed"]) == 2104001
        assert [row[f"p{i}"] for i in range(1, 5)] == (
            plan["models"][index:] + plan["models"][:index]
        )
    assert plan["checkpoint_after"] == 1
    assert plan["budget"]["max_cost_per_match_eur"] == 0.16
    assert 4 * plan["budget"]["match_cap_eur"] <= plan["budget"]["stage_eur"] == 1.00
