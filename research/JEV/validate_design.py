"""Check the proposed design and illustrative math, without network or model clients."""

from pathlib import Path

import yaml

plan = yaml.safe_load(Path(__file__).with_name("PLAN.yaml").read_text(encoding="utf-8"))
assert plan["implementation_mode"] == "fake_only"
assert plan["real_call_approvals"] == []
assert plan["budget"]["approved_real_eur"] == 0
assert plan["budget"]["automatic_retries"] == 0
assert plan["budget"]["proposed_real_eur"] <= plan["budget"]["per_job_ceiling_eur"]
repair = plan["repair"]
referee = plan["referee"]
assert repair["development_target"] + repair["validation_target"] == repair["target_cases"]
assert 100 <= repair["target_cases"] <= 200
assert plan["budget"]["max_real_requests_if_separately_approved"] == (
    repair["target_cases"] + referee["target_matches"]
)
assert repair["threshold_statistic"] == "maximum_returned_option_probability"
assert repair["free_text_repair"] == "forbidden"
assert repair["strategic_recommendation_or_missing_amount_guess"] == "forbidden"

# Illustrations only, not empirical calibration: exact one-sided lower bound
# when every accepted independent case is correct, alpha=.05.
lower_20 = 0.05 ** (1 / 20)
lower_58 = 0.05 ** (1 / 58)
lower_59 = 0.05 ** (1 / 59)
assert lower_20 < 0.87
assert lower_58 < 0.95 <= lower_59

# A concentration score can differ across option counts at the same p_top.
p_top = 0.90
confidence_2 = (p_top - 1 / 2) / (1 - 1 / 2)
confidence_10 = (p_top - 1 / 10) / (1 - 1 / 10)
assert confidence_2 < confidence_10
print("Design guards passed; no network/model client imported or called.")
print(f"Illustrative zero-error lower bounds: n20={lower_20:.6f}; n59={lower_59:.6f}")
print(f"Concentration at p_top=.90: n2={confidence_2:.6f}; n10={confidence_10:.6f}")
