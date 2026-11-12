"""C1 custom proposal stays outside executable experiment discovery."""

from pathlib import Path

import yaml


def test_c1_design_is_unapproved_and_keeps_factors_separate():
    root = Path(__file__).resolve().parents[2]
    plan = yaml.safe_load((root / "research/C1/PLAN.yaml").read_text())
    assert plan["schema"] == "civ_design_only_v1"
    assert not plan["execution_approved"]
    assert plan["approved_budget_eur"] == 0
    assert plan["requested_preset"]["round_limit_api_setting"] == "rounds"
    assert plan["requested_preset"]["rounds"] == 20
    assert len(plan["models"]) == 4
    assert plan["baseline"]["expected_base_calls_upper"] == 80
    assert plan["baseline"]["strategy_text"] == "off"
    assert plan["baseline"]["private_plan"] == "off"
    assert plan["later_factorial"]["prompt_version"] == "civ-p1"
    assert plan["later_factorial"]["total_cells_including_baseline"] == 16
    assert not (root / "experiments/C1_civ_pilot.yaml").exists()
