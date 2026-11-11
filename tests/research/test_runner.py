"""The batch runner, against a fake arena API: budgets, the pilot rule, resuming, retries."""

import itertools
import json

import pytest
import yaml

from arena.research.experiment import PlanError, load_experiment
from arena.research.runner import (
    MatchReport,
    Runner,
    RunStopped,
    SeatReport,
    main,
    pilot_problems,
    seat_reports,
)
from tests.research.test_experiment import E1


class FakeArena:
    """Plays every match at once. `cost` and `status` say what each match turns into."""

    def __init__(self, cost=10_000, status="finished", fallbacks=None):
        self.cost = cost  # micro-euro per match, or a function of the match number
        self.status = status  # a status, or a function of the match number
        self.fallbacks = fallbacks or {}  # model -> fallback turns per match (of 10)
        self.started = []
        self.ids = itertools.count(1)
        self.records = {}

    def __call__(self, method, path, body):
        if method == "POST" and path == "/matches":
            number = next(self.ids)
            match_id = f"m{number}"
            self.started.append(body)
            status = self.status(number) if callable(self.status) else self.status
            self.records[match_id] = {
                "status": "running",
                "final": status,
                "number": number,
                "seats": body.get("models") or ["bot"] * body["players"],
            }
            return 201, {"id": match_id, "status": "running"}
        match_id = path.split("/")[2]
        record = self.records[match_id]
        if path.endswith("/events"):
            events = []
            for seat, model in enumerate(record["seats"], start=1):
                bad = self.fallbacks.get(model, 0)
                for turn in range(10):
                    kind = "action_fallback" if turn < bad else "action_accepted"
                    events.append({"type": kind, "data": {"player": f"p{seat}"}})
            return 200, events
        if path.endswith("/cost"):
            cost = self.cost(record["number"]) if callable(self.cost) else self.cost
            return 200, {"total_micro_eur": cost, "players": {}}
        record["status"] = record["final"]
        return 200, {
            "id": match_id,
            "status": record["status"],
            "placements": [{"player": "p1", "rank": 1}],
            "prompt_version": "liars_deck-p1",
        }


def runner(tmp_path, arena, **options):
    return Runner(
        load_experiment(E1),
        "A",
        tmp_path,
        arena,
        sleep=lambda _: None,
        say=lambda _: None,
        **options,
    )


def _lines(tmp_path):
    return (tmp_path / "runs.jsonl").read_text(encoding="utf-8").splitlines()


def test_pilot_plays_the_eight_pilot_matches_with_model_seats_and_logs_them(tmp_path):
    arena = FakeArena()

    reports = runner(tmp_path, arena, pilot=True).run()

    assert [r.order for r in reports] == list(range(1, 9))
    assert all(b["confirm_spend"] is True and len(b["models"]) == 4 for b in arena.started)
    assert {body["seed"] for body in arena.started} == {1101011, 1101021}
    assert all(body["settings"]["variant"] == "base" for body in arena.started)
    assert len(_lines(tmp_path)) == 8
    assert json.loads(_lines(tmp_path)[0])["prompt_version"] == "liars_deck-p1"
    assert (tmp_path / "001.json").exists()


def test_extra_settings_reach_every_match(tmp_path):
    arena = FakeArena()

    runner(tmp_path, arena, pilot=True, settings={"prompt_version": "liars_deck-p1"}).run()

    assert all(b["settings"]["prompt_version"] == "liars_deck-p1" for b in arena.started)


def test_bots_send_no_models(tmp_path):
    arena = FakeArena(cost=0)

    runner(tmp_path, arena, pilot=True, bots=True).run()

    assert all("models" not in body and body["players"] == 4 for body in arena.started)


def test_run_stops_at_90_percent_of_the_budget(tmp_path):
    # Pilot budget 0.30 EUR; one match of 0.27 EUR is 90 %.
    arena = FakeArena(cost=270_000)

    with pytest.raises(RunStopped, match="90 %"):
        runner(tmp_path, arena, pilot=True).run()
    assert len(arena.started) == 1


def test_run_stops_when_two_more_mean_matches_would_pass_the_budget(tmp_path):
    # 0.07 EUR per match: after 3 matches 0.21, plus 2 x 0.07 = 0.35 > 0.30.
    arena = FakeArena(cost=70_000)

    with pytest.raises(RunStopped, match="twice the mean"):
        runner(tmp_path, arena, pilot=True).run()
    assert len(arena.started) == 3


def test_pilot_rule_stops_a_model_with_too_many_fallbacks(tmp_path):
    with pytest.raises(RunStopped, match="llama-scout: 20%"):
        runner(tmp_path, FakeArena(fallbacks={"llama-scout": 2}), pilot=True).run()
    # The league does not start after a pilot that broke the rule.
    league = FakeArena()
    with pytest.raises(RunStopped, match="pilot rule broken"):
        runner(tmp_path, league).run()
    assert league.started == []


def test_a_fallback_share_of_ten_percent_passes(tmp_path):
    runner(tmp_path, FakeArena(fallbacks={"llama-scout": 1}), pilot=True).run()


def test_a_second_start_continues_after_the_last_logged_match(tmp_path):
    first = FakeArena()
    pilot = runner(tmp_path, first, pilot=True)
    pilot.play(pilot.matches[0])
    pilot.play(pilot.matches[1])
    second = FakeArena()

    reports = runner(tmp_path, second, pilot=True).run()

    assert len(second.started) == 6
    assert [r.order for r in reports] == list(range(1, 9))


def test_a_failed_match_is_played_once_more_and_both_attempts_are_kept(tmp_path):
    arena = FakeArena(status=lambda n: "failed" if n in (1, 2) else "finished")

    reports = runner(tmp_path, arena, pilot=True).run()

    assert len(arena.started) == 9  # the first match failed twice and is then missing
    assert reports[0].status == "failed" and reports[0].attempt == 2
    assert (tmp_path / "001-attempt2.json").exists()
    assert len(_lines(tmp_path)) == 9


def test_a_refused_start_stops_the_run(tmp_path):
    def refuse(method, path, body):
        return 403, {"detail": "Model seats make paid calls and are off on this server."}

    with pytest.raises(RunStopped, match="403"):
        runner(tmp_path, refuse, pilot=True).run()


def test_a_match_without_its_cost_stops_the_run(tmp_path):
    arena = FakeArena()

    def no_cost(method, path, body):
        if path.endswith("/cost"):
            return 503, {"detail": "ledger down"}
        return arena(method, path, body)

    with pytest.raises(RunStopped, match="ledger"):
        runner(tmp_path, no_cost, pilot=True).run()
    assert len(arena.started) == 1


def test_a_stage_without_approval_may_not_spend(tmp_path):
    data = yaml.safe_load(E1.read_text(encoding="utf-8"))
    data["approvals"] = []
    plan = tmp_path / "plan.yaml"
    plan.write_text(yaml.safe_dump(data), encoding="utf-8")

    with pytest.raises(PlanError, match="approvals"):
        Runner(load_experiment(plan), "A", tmp_path, FakeArena())
    Runner(load_experiment(plan), "A", tmp_path, FakeArena(), bots=True)  # bots are free


def test_only_a_league_has_a_pilot_and_the_stage_must_exist(tmp_path):
    with pytest.raises(PlanError, match="no pilot"):
        Runner(load_experiment(E1), "B", tmp_path, FakeArena(), pilot=True)
    with pytest.raises(PlanError, match="no stage"):
        Runner(load_experiment(E1), "Z", tmp_path, FakeArena())


def test_seat_reports_count_turns_fallbacks_rejections_and_failed_agents():
    events = [
        {"type": "action_rejected", "data": {"player": "p1"}},
        {"type": "action_accepted", "data": {"player": "p1"}},
        {"type": "agent_failed", "data": {"player": "p2", "error": "x"}},
        {"type": "action_fallback", "data": {"player": "p2", "reason": "agent_failed"}},
        {"type": "thought", "data": {"player": "p1", "text": "hm"}},
        {"type": "cards_played", "data": {"player": "p9"}},
    ]

    reports = seat_reports(events, {"p1": "a", "p2": "b"})

    assert (reports["p1"].turns, reports["p1"].rejected, reports["p1"].fallbacks) == (1, 1, 0)
    p2 = reports["p2"]
    assert (p2.turns, p2.fallbacks, p2.agent_failed) == (1, 1, True)


def test_pilot_problems_name_a_model_whose_agent_failed_twice():
    def report(order, failed):
        seat = SeatReport("a", turns=10, agent_failed=failed)
        return MatchReport(
            order, "A", "T01", 1, 1, 1, True, f"m{order}", "finished", 0, [], {"p1": seat}
        )

    assert pilot_problems([report(1, True), report(2, False)]) == []
    assert pilot_problems([report(1, True), report(2, True)]) == ["a: agent failed in 2 matches"]


def test_command_needs_a_seat_choice_and_reports_a_bad_stage(tmp_path, capsys):
    with pytest.raises(SystemExit):
        main([str(E1), "--stage", "A", "--out", str(tmp_path)])
    assert main([str(E1), "--stage", "Z", "--out", str(tmp_path), "--bots"]) == 2
    assert "no stage" in capsys.readouterr().err
