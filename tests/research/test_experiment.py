"""Experiment plans: the files under experiments/ load, fit the cap and fix their schedule."""

import io
from collections import Counter
from itertools import combinations
from pathlib import Path

import pytest
import yaml

from arena.config import load_config
from arena.research.experiment import PlanError, load_experiment, main, schedule, write_csv
from arena.research.power import detectable

EXPERIMENTS = Path(__file__).resolve().parents[2] / "experiments"
E1 = EXPERIMENTS / "E1_liars_deck.yaml"


def _models(seats):
    return [seat.split("@")[0] for seat in seats]


def _changed(tmp_path, change):
    data = yaml.safe_load(E1.read_text(encoding="utf-8"))
    change(data)
    path = tmp_path / "plan.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


@pytest.mark.parametrize("path", sorted(EXPERIMENTS.glob("*.yaml")), ids=lambda path: path.stem)
def test_every_plan_loads_and_its_stored_schedule_is_the_one_it_fixes(path):
    out = io.StringIO()
    write_csv(schedule(load_experiment(path)), out)

    stored = path.with_name(f"{path.stem}_schedule.csv").read_text(encoding="utf-8")
    assert stored == out.getvalue()


def test_the_same_plan_gives_the_same_schedule():
    assert schedule(load_experiment(E1)) == schedule(load_experiment(E1))


def test_league_stage_is_balanced_over_models_seats_and_seeds():
    matches = [match for match in schedule(load_experiment(E1)) if match.stage == "A"]

    assert len(matches) == 112
    played = Counter(model for match in matches for model in _models(match.seats))
    assert len(played) == 8 and set(played.values()) == {56}
    seat_of = Counter(
        (model, seat) for match in matches for seat, model in enumerate(_models(match.seats))
    )
    assert set(seat_of.values()) == {14}
    # One seed is one table with its four seatings.
    for seed in {match.seed for match in matches}:
        same = [match for match in matches if match.seed == seed]
        assert len(same) == 4
        assert len({frozenset(match.seats) for match in same}) == 1


def test_pilot_matches_come_first_and_seat_every_league_model_in_every_seat():
    matches = schedule(load_experiment(E1))
    pilot = [match for match in matches if match.pilot]

    assert [match.order for match in pilot] == list(range(1, 9))
    seat_of = Counter(
        (model, seat) for match in pilot for seat, model in enumerate(_models(match.seats))
    )
    assert len(seat_of) == 32 and set(seat_of.values()) == {1}


def test_a_stage_plays_whole_replicates_one_after_the_other():
    for stage in "ABC":
        matches = [match for match in schedule(load_experiment(E1)) if match.stage == stage]
        replicates = [match.replicate for match in matches if not match.pilot]
        assert replicates == sorted(replicates)


def test_mirror_stage_gives_each_model_both_efforts_in_every_seat_equally():
    matches = [match for match in schedule(load_experiment(E1)) if match.stage == "B"]

    assert len(matches) == 96
    for match in matches:
        assert len(set(_models(match.seats))) == 1
        assert Counter(seat.split("@")[1] for seat in match.seats) == {"high": 2, "low": 2}
    seat_of = Counter((seat, place) for match in matches for place, seat in enumerate(match.seats))
    assert len(seat_of) == 4 * 2 * 4 and set(seat_of.values()) == {12}
    assert len({match.seed for match in matches}) == 4


def test_guest_stage_seats_each_guest_six_times_per_seat_with_the_three_hosts():
    experiment = load_experiment(E1)
    stage = next(stage for stage in experiment.stages if stage.id == "C")
    matches = [match for match in schedule(experiment) if match.stage == "C"]

    assert len(matches) == 96
    for guest in stage.guests:
        own = [match for match in matches if match.table == guest]
        assert all(sorted(_models(m.seats)) == sorted([guest, *stage.hosts]) for m in own)
        assert Counter(_models(m.seats).index(guest) for m in own) == {0: 6, 1: 6, 2: 6, 3: 6}


def test_seeds_of_different_stages_never_meet():
    matches = schedule(load_experiment(E1))
    stages = ["A", "A2", "B", "C"]
    seeds = {stage: {m.seed for m in matches if m.stage == stage} for stage in stages}

    for first, second in combinations(stages, 2):
        assert not seeds[first] & seeds[second], (first, second)


def test_six_model_league_is_balanced_over_models_pairs_seats_and_seeds():
    experiment = load_experiment(E1)
    stage = next(stage for stage in experiment.stages if stage.id == "A2")
    matches = [match for match in schedule(experiment) if match.stage == "A2"]

    assert len(matches) == 120 and not any(match.pilot for match in matches)
    played = Counter(model for match in matches for model in _models(match.seats))
    assert played == dict.fromkeys(stage.models, 80)
    seat_of = Counter(
        (model, seat) for match in matches for seat, model in enumerate(_models(match.seats))
    )
    assert len(seat_of) == 24 and set(seat_of.values()) == {20}
    pairs = Counter(
        pair
        for match in matches
        if match.seating == 1 and match.replicate == 1
        for pair in combinations(sorted(_models(match.seats)), 2)
    )
    assert len(pairs) == 15 and set(pairs.values()) == {6}
    assert {"qwen-flash", "gemini-flash-lite"}.isdisjoint(played)


def test_version_2_is_an_amendment_with_its_own_approval():
    experiment = load_experiment(E1)

    assert experiment.version == 2
    assert [entry["version"] for entry in experiment.amendments] == [2]
    assert any("A2" in entry["stages"] for entry in experiment.approvals)
    stage_a = next(stage for stage in experiment.stages if stage.id == "A")
    assert stage_a.budget_eur == stage_a.pilot_budget_eur


def test_roster_models_in_the_plan_match_the_config():
    """A model that is in config/models.yaml must be the same model at the same price."""
    experiment = load_experiment(E1)
    config = load_config()
    shared = set(experiment.models) & set(config.models)

    assert len(shared) >= 8
    for model_id in shared:
        planned, known = experiment.models[model_id], config.models[model_id]
        assert planned.openrouter == known.model
        assert planned.input_usd_per_mtok == known.input_usd_per_mtok
        assert planned.output_usd_per_mtok == known.output_usd_per_mtok


def test_plan_leaves_a_fifth_of_the_cap_unplanned():
    budget = load_experiment(E1).budget

    assert budget.reserve_eur >= budget.month_cap_eur / 5


def test_power_numbers_quoted_in_the_plan_are_the_computed_ones():
    text = load_experiment(E1).analysis["power"]

    quoted = {
        "0.48": detectable(56, 0.25, 0.05 / 8),
        "0.44": detectable(56, 0.25, 0.05),
        "0.66": detectable(96, 0.5, 0.05),
        "0.61": detectable(24, 0.25, 0.05 / 4),
        "0.40": detectable(96, 0.25, 0.05),
        "0.45": detectable(48, 0.25, 0.05),
    }
    for shown, computed in quoted.items():
        assert shown in text
        assert f"{computed:.2f}" == shown


def test_budgets_above_the_monthly_cap_are_refused(tmp_path):
    def raise_stage_budget(data):
        data["stages"][0]["budget_eur"] = 30.00

    with pytest.raises(PlanError, match="above the monthly cap"):
        load_experiment(_changed(tmp_path, raise_stage_budget))


def test_a_pilot_budget_above_its_stage_budget_is_refused(tmp_path):
    def raise_pilot_budget(data):
        data["stages"][0]["pilot_budget_eur"] = 3.50

    with pytest.raises(PlanError, match="pilot budget"):
        load_experiment(_changed(tmp_path, raise_pilot_budget))


def test_a_stage_with_a_model_the_plan_does_not_list_is_refused(tmp_path):
    def name_unknown_model(data):
        data["stages"][1]["models"][0] = "nobody"

    with pytest.raises(PlanError, match="nobody"):
        load_experiment(_changed(tmp_path, name_unknown_model))


def test_an_unknown_field_is_refused(tmp_path):
    def add_field(data):
        data["stages"][0]["sedes"] = 3

    with pytest.raises(PlanError, match="sedes"):
        load_experiment(_changed(tmp_path, add_field))


def test_a_file_that_cannot_be_read_is_a_plan_error(tmp_path):
    with pytest.raises(PlanError, match="cannot read"):
        load_experiment(tmp_path / "missing.yaml")


def test_command_prints_the_schedule_and_reports_a_broken_plan(tmp_path, capsys):
    assert main([str(E1)]) == 0
    printed = capsys.readouterr().out
    assert printed.splitlines()[0] == "order,stage,table,seating,replicate,seed,pilot,p1,p2,p3,p4"
    assert len(printed.splitlines()) == 425

    broken = tmp_path / "broken.yaml"
    broken.write_text("id: E0\n", encoding="utf-8")
    assert main([str(broken)]) == 1
    assert "broken.yaml" in capsys.readouterr().err
    assert main([]) == 2
