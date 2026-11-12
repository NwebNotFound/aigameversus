"""The W2 guest-stage client against a fake arena: no server, no model, nothing spent."""

import json
import shutil
from pathlib import Path

import pytest
import yaml

from arena.research.runner import RunStopped
from arena.research.stage_runner import PlanRefused, StageRunner

ROOT = Path(__file__).resolve().parents[2]
PLAN = ROOT / "research/W2/PLAN.yaml"


class FakeArena:
    """Answers the client's calls like the arena; every call is kept in `calls`."""

    def __init__(self, plan, **override):
        self.plan = plan
        self.calls = []
        self.matches = {}
        self.month = override.get("month", 3_756_279)
        self.estimate = override.get("estimate", 241_947)
        self.cap = override.get("cap", 400_000)
        self.ledger_cap = override.get("ledger_cap", 0.5)  # limits.match_eur of the arena
        self.cost = override.get("cost", 200_000)
        self.players = override.get("players", ["p1", "p2", "p3", "p4"])
        self.turns = override.get("turns", {})  # seat -> (accepted, fallback)
        self.paused = override.get("paused", False)
        self.running = override.get("running", [])
        self.prices = {g["id"]: dict(g) for g in plan.get("guests", [])}
        self.status = override.get("status", "finished")
        self.guest_turns = override.get("guest_turns", (10, 0))  # accepted, fallback
        self.role = override.get("role")  # None: the planned one
        self.agent_failed = override.get("agent_failed", False)
        self.lose_post = 0  # POSTs that raise after creating (1) or without creating (2)

    def __call__(self, method, path, body):
        self.calls.append((method, path, body))
        if method == "GET" and path == "/setup":
            return 200, {"caps": {"match_eur": self.ledger_cap, "month_eur": 25}}
        if method == "GET" and path == "/ledger/month":
            return 200, {
                "spent_micro_eur": self.month,
                "remaining_micro_eur": 25_000_000 - self.month,
            }
        if method == "GET" and path == "/matches?status=running":
            return 200, self.running
        if method == "GET" and path.startswith("/matches?batch="):
            return 200, list(self.matches.values())
        if method == "POST" and path == "/matches/estimate":
            return 200, {"estimate_micro_eur": self.estimate, "cap_micro_eur": self.cap}
        if method == "GET" and path == "/models/catalog":
            return 200, {"models": list(self.prices.values())}
        if method == "POST" and path == "/matches":
            if self.lose_post == 2:
                raise TimeoutError("no answer")
            match_id = f"m{len(self.matches) + 1}"
            self.matches[match_id] = {
                "id": match_id,
                "status": self.status,
                "batch": body["batch"],
                "settings": body["settings"],
                "prompt_version": "werewolf-p2",
                "body": body,
            }
            if self.lose_post == 1:
                raise TimeoutError("no answer")
            return 201, self.matches[match_id]
        if method == "GET" and path.endswith("/events"):
            match = self.matches[path.split("/")[2]]
            seat = next(r for r in self.rows if int(r["order"]) == match["batch"]["index"])
            players = [seat["guest_seat"]] if seat.get("guest_seat") else self.players
            events = []
            if seat.get("guest_seat"):
                role = self.role or seat["expected_role"]
                events.append(
                    {"type": "role_assigned", "data": {"player": players[0], "role": role}}
                )
            for player in players:
                accepted, fallback = self.turns.get(player, self.guest_turns)
                events += [{"type": "action_accepted", "data": {"player": player}}] * accepted
                events += [{"type": "action_fallback", "data": {"player": player}}] * fallback
            if self.agent_failed:
                events.append({"type": "agent_failed", "data": {"player": "p1"}})
            return 200, events
        if method == "GET" and path.endswith("/control"):
            return 200, {"paused": self.paused, "turn_delay": 0}
        if method == "GET" and path.endswith("/cost"):
            return 200, {"total_micro_eur": self.cost}
        if method == "GET" and path.startswith("/matches/"):
            return 200, {k: v for k, v in self.matches[path.split("/")[2]].items() if k != "body"}
        raise AssertionError(f"unexpected call {method} {path}")

    def posts(self):
        return [body for method, path, body in self.calls if (method, path) == ("POST", "/matches")]


@pytest.fixture
def approved(tmp_path):
    """The W2 plan as on main, with its execution approval recorded (as the Researcher will)."""
    folder = tmp_path / "W2"
    folder.mkdir()
    plan = yaml.safe_load(PLAN.read_text(encoding="utf-8"))
    plan["execution_plan_approved"] = True
    plan["execution_approval_evidence"] = "Lead message 23b25e1b (test)"
    (folder / "PLAN.yaml").write_text(yaml.safe_dump(plan, sort_keys=False), encoding="utf-8")
    shutil.copy(PLAN.parent / plan["schedule"], folder / plan["schedule"])
    return folder / "PLAN.yaml"


EVIDENCE = {"pre_start_report": "PR #165 comment (test)", "arena_build": "main abc123 (test)"}


def client(plan_path, out, arena, **kwargs):
    kwargs.setdefault("evidence", EVIDENCE)
    runner = StageRunner(
        plan_path, out, arena, poll=0, sleep=lambda s: None, say=lambda m: None, **kwargs
    )
    arena.rows = runner.matches
    return runner


def arena_for(plan_path, **override):
    return FakeArena(yaml.safe_load(plan_path.read_text(encoding="utf-8")), **override)


def test_the_plan_on_main_may_not_start_without_its_execution_approval(tmp_path):
    with pytest.raises(PlanRefused, match="execution approval"):
        StageRunner(PLAN, tmp_path / "out", arena_for(PLAN))


def test_a_schedule_that_is_not_the_plans_own_is_refused(approved, tmp_path):
    csv = approved.parent / "schedule.csv"
    lines = csv.read_text(encoding="utf-8").splitlines()
    lines[1] = lines[1].replace("glm-flash", "qwen-flash", 1)  # a host swapped
    csv.write_text("\n".join(lines) + "\n", encoding="utf-8")

    with pytest.raises(PlanRefused, match="not the schedule"):
        StageRunner(approved, tmp_path / "out", arena_for(approved))


def test_all_eight_rows_play_serially_with_only_whitelisted_fields(approved, tmp_path):
    arena = arena_for(approved)

    ended = client(approved, tmp_path / "out", arena).run()

    assert len(ended) == 8 and len(arena.posts()) == 8
    plan = yaml.safe_load(approved.read_text(encoding="utf-8"))
    for body, row in zip(
        arena.posts(), client(approved, tmp_path / "x", arena).matches, strict=True
    ):
        assert set(body) == {
            "game",
            "seed",
            "models",
            "settings",
            "memory",
            "confirm_spend",
            "batch",
        }
        assert body["settings"] == plan["settings"] and body["memory"] is False
        assert body["models"] == [row[f"p{i}"] for i in range(1, 9)]
        assert "expected_role" not in json.dumps(body) and 'werewolf"' not in json.dumps(
            body["batch"]
        )
    # Every start was written down before its POST.
    lines = [
        json.loads(line) for line in (tmp_path / "out/attempts.jsonl").read_text().splitlines()
    ]
    first = next(i for i, line in enumerate(lines) if line.get("state") == "starting")
    started = next(i for i, line in enumerate(lines) if line.get("state") == "started")
    assert first < started and lines[first]["plan_sha256"] and lines[first]["estimate_micro_eur"]
    assert sorted(f.name for f in (tmp_path / "out").glob("*.json"))[0].startswith("001-")


@pytest.mark.parametrize(
    ("override", "says"),
    [
        ({"month": 20_000_000}, "the month has spent"),
        ({"running": [{"id": "other"}]}, "serial only"),
        ({"estimate": 400_000}, "not below the match cap"),
        ({"cap": 500_000}, "not in force"),
        ({"estimate": 1_100_000, "cap": 400_000}, "not below the match cap"),
    ],
)
def test_a_gate_that_fails_holds_before_any_start(approved, tmp_path, override, says):
    arena = arena_for(approved, **override)

    with pytest.raises(RunStopped, match=says):
        client(approved, tmp_path / "out", arena).run()

    assert arena.posts() == []


def test_a_price_above_the_plans_holds(approved, tmp_path):
    arena = arena_for(approved)
    first_guest = client(approved, tmp_path / "x", arena).matches[0]["guest"]
    arena.prices[first_guest]["output_usd_per_mtok"] += 0.5

    with pytest.raises(RunStopped, match="above the plan's"):
        client(approved, tmp_path / "out", arena).run()

    assert arena.posts() == []


def test_the_shared_stage_budget_counts_every_attempt_and_both_reserves(approved, tmp_path):
    # Each match bills 0.39 EUR and is quoted at 0.20: before row 8, 7 x 0.39 + 3 x 0.20 =
    # 3.33 EUR passes 90 % of 3.50 (3.15), so the eighth never starts.
    arena = arena_for(approved, cost=390_000, estimate=200_000)

    with pytest.raises(RunStopped, match="90% of the stage"):
        client(approved, tmp_path / "out", arena).run()

    assert len(arena.posts()) == 7
    # A new client (a restart) counts the same spend: the allowance does not reset.
    again = arena_for(approved, cost=390_000, estimate=200_000)
    with pytest.raises(RunStopped, match="90% of the stage"):
        client(approved, tmp_path / "out", again).run()
    assert again.posts() == []


def test_the_tables_limit_is_held_for_the_next_match_and_a_lost_start_counts_at_it(
    approved, tmp_path
):
    runner = client(approved, tmp_path / "out", arena_for(approved))
    for order in range(1, 7):
        runner._write(
            {"attempt_id": f"a{order}", "order": order, "state": "ended", "cost_micro_eur": 400_000}
        )
    runner._write({"attempt_id": "x", "order": 99, "state": "started", "match_id": "lost"})
    # 6 x 0.40 + the lost start at the table's limit 0.40 = 2.80 EUR; 3 x a tiny quote fits
    # 90 % (2.803 <= 3.15). One more ended match at 0.32 makes 3.12: 3 x the quote still fits
    # 90 % (3.123), but + the table's limit 0.40 = 3.52 > 3.50.
    runner._write({"attempt_id": "a7", "order": 7, "state": "ended", "cost_micro_eur": 320_000})
    arena = arena_for(approved, estimate=1_000)

    with pytest.raises(RunStopped, match="the reserve 0.40"):
        client(approved, tmp_path / "out", arena).gates(runner.matches[7])
    assert arena.posts() == []
    # The lost start is what tips it: counted at 0 the same row would pass.
    assert client(approved, tmp_path / "out", arena).spent() == 3_120_000


@pytest.mark.parametrize(
    ("override", "says"),
    [
        ({"status": "interrupted"}, "match interrupted"),
        ({"agent_failed": True}, "a failed agent"),
        ({"guest_turns": (8, 2)}, "fallback share 20% \\(p4"),
        ({"role": "villager"}, "guest dealt villager"),
    ],
)
def test_a_bad_match_holds_and_is_never_replayed(approved, tmp_path, override, says):
    arena = arena_for(approved, **override)

    with pytest.raises(RunStopped, match=says):
        client(approved, tmp_path / "out", arena).run()
    assert len(arena.posts()) == 1
    with pytest.raises(RunStopped, match="resume-after-hold"):
        client(approved, tmp_path / "out", arena).run()  # held until a person decides
    assert len(arena.posts()) == 1

    good = arena_for(approved)
    ended = client(approved, tmp_path / "out", good, resume_after_hold=True).run()
    assert len(good.posts()) == 7  # row 1 is not played again
    assert len(ended) == 8


def test_a_post_without_an_answer_adopts_the_match_it_started(approved, tmp_path):
    arena = arena_for(approved)
    arena.lose_post = 1  # the arena created the match, the answer was lost
    runner = client(approved, tmp_path / "out", arena)

    with pytest.raises(StopIteration):  # stop after the first row for this test
        arena.after = iter(())
        original = runner._finish

        def first_only(attempt_id, attempt):
            original(attempt_id, attempt)
            next(arena.after)

        runner._finish = first_only
        runner.run()

    assert len(arena.matches) == 1 and len(arena.posts()) == 1  # adopted, not posted again
    (attempt,) = [a for a in runner.attempts().values()]
    assert attempt["match_id"] == "m1" and attempt["state"] == "ended"


def test_a_post_that_shows_no_match_holds_until_a_person_marks_it_unstarted(approved, tmp_path):
    arena = arena_for(approved)
    arena.lose_post = 2  # no answer, and no match was created
    out = tmp_path / "out"

    first = client(approved, out, arena)
    with pytest.raises(RunStopped, match="--mark-unstarted"):
        first.run()
    assert arena.matches == {}
    (attempt,) = first.attempts().values()
    arena.lose_post = 0
    # Absence from the batch proves nothing: every later run holds, it never reposts.
    for _ in range(2):
        with pytest.raises(RunStopped, match="may have started a match"):
            client(approved, out, arena).run()
    assert len(arena.posts()) == 1

    with pytest.raises(PlanRefused):
        client(approved, out, arena).mark_unstarted(attempt["attempt_id"], " ")
    client(approved, out, arena).mark_unstarted(attempt["attempt_id"], "checked GET /matches")
    ended = client(approved, out, arena).run()
    assert len(arena.matches) == 8 and len(ended) == 8  # row 1 once, then the rest


def test_a_match_running_when_the_client_stopped_is_waited_for_not_started_again(
    approved, tmp_path
):
    arena = arena_for(approved)
    out = tmp_path / "out"
    runner = client(approved, out, arena)
    row = runner.matches[0]
    status, record = arena("POST", "/matches", runner.body(row, "abc123"))
    runner._write({"attempt_id": "abc123", "order": 1, "guest": row["guest"], "state": "starting"})
    runner._write({"attempt_id": "abc123", "match_id": record["id"], "state": "started"})

    ended = client(approved, out, arena).run()

    assert len(arena.matches) == 8 and len(ended) == 8
    assert [b["batch"]["index"] for b in arena.posts()] == list(range(1, 9))  # row 1 only once


C1_SCHEDULE = """order,seed,p1,p2,p3,p4
1,2104001,glm-flash,deepseek-flash,gpt-luna,claude-haiku
2,2104001,deepseek-flash,gpt-luna,claude-haiku,glm-flash
3,2104001,gpt-luna,claude-haiku,glm-flash,deepseek-flash
4,2104001,claude-haiku,glm-flash,deepseek-flash,gpt-luna
"""


@pytest.fixture
def c1(tmp_path):
    """A C1-shaped job: 4 seats, no guest, a checkpoint after the first match (example data)."""
    folder = tmp_path / "C1"
    folder.mkdir()
    plan = {
        "id": "C1",
        "schema": "explicit_stage_v1",
        "game": "civ",
        "execution_plan_approved": True,
        "execution_approval_evidence": "Lead 454cd9d8 (test)",
        "schedule": "schedule.csv",
        "settings": {
            "rounds": 20,
            "prompt_version": "civ-p1",
            "strategy_text": "off",
            "private_plan": "off",
            "answer_repair": "off",
            "match_budget_eur": 0.2,
        },
        "memory": False,
        "max_matches": 4,
        "checkpoint_after": 1,
        "budget": {
            "stage_eur": 1.0,
            "match_cap_eur": 0.2,
            "stop_start_share": 0.9,
            "notify_and_hold_at_month_eur": 20,
            "automatic_retries": 0,
            "max_cost_per_match_eur": 0.16,
        },
    }
    (folder / "PLAN.yaml").write_text(yaml.safe_dump(plan, sort_keys=False), encoding="utf-8")
    (folder / "schedule.csv").write_text(C1_SCHEDULE, encoding="utf-8")
    return folder / "PLAN.yaml"


def c1_arena(plan_path, **override):
    return arena_for(plan_path, **{"cap": 200_000, "estimate": 60_000, "cost": 100_000, **override})


def test_a_c1_job_plays_one_match_then_holds_at_the_checkpoint_even_after_a_restart(c1, tmp_path):
    out = tmp_path / "out"
    arena = c1_arena(c1)

    with pytest.raises(RunStopped, match="review checkpoint after 1"):
        client(c1, out, arena).run()
    assert len(arena.posts()) == 1
    body = arena.posts()[0]
    assert body["game"] == "civ" and body["models"] == [
        "glm-flash",
        "deepseek-flash",
        "gpt-luna",
        "claude-haiku",
    ]
    assert body["settings"]["match_budget_eur"] == 0.2 and body["settings"]["rounds"] == 20

    with pytest.raises(RunStopped, match="review checkpoint"):
        client(c1, out, arena).run()  # a restart stays held
    assert len(arena.posts()) == 1

    with pytest.raises(PlanRefused):
        client(c1, out, arena).release_checkpoint("  ")  # a release needs its evidence
    client(c1, out, arena).release_checkpoint("Researcher review 2026-11-12 (test)")
    ended = client(c1, out, arena).run()
    assert len(ended) == 4 and len(arena.posts()) == 4
    summary = json.loads((out / "run.json").read_text())
    assert summary["stage_spent_micro_eur"] == summary["booked_micro_eur"] == 400_000
    assert summary["cap_read_back_micro_eur"] == 200_000 and summary["match_budget_eur"] == 0.2
    assert summary["reserve_micro_eur"] == 200_000  # the table's own limit
    assert summary["released_after"] == 1 and len(summary["attempts"]) == 4


def test_a_c1_match_above_its_cost_stop_holds(c1, tmp_path):
    arena = c1_arena(c1, cost=170_000)

    with pytest.raises(RunStopped, match="above the stop of 0.16"):
        client(c1, tmp_path / "out", arena).run()

    assert len(arena.posts()) == 1


def test_without_a_guest_every_models_fallback_share_counts(c1, tmp_path):
    arena = c1_arena(c1, turns={"p3": (8, 2)})  # gpt-luna on p3 in row 1

    with pytest.raises(RunStopped, match="fallback share 20% \\(p3: gpt-luna\\)"):
        client(c1, tmp_path / "out", arena).run()


def test_a_dry_run_estimates_every_open_row_and_spends_nothing(c1, tmp_path):
    arena = c1_arena(c1)
    out = tmp_path / "out"

    report = client(c1, out, arena, dry_run=True).run()

    assert [row["order"] for row in report] == [1, 2, 3, 4]
    assert all(row["ok"] and row["estimate_micro_eur"] == 60_000 for row in report)
    assert arena.posts() == [] and not (out / "attempts.jsonl").exists()
    assert json.loads((out / "dry-run.json").read_text()) == report
    held = client(c1, out, c1_arena(c1, estimate=200_000), dry_run=True).run()
    assert not any(row["ok"] for row in held) and "not below the match cap" in held[0]["hold"]


@pytest.mark.parametrize(
    "schedule",
    [
        C1_SCHEDULE.replace("order,seed,p1", "order,seed,notes,p1").replace(
            "1,2104001,glm", "1,2104001,x,glm"
        ),
        C1_SCHEDULE.replace("\n3,", "\n5,"),  # a gap in the order
        C1_SCHEDULE.rsplit("4,2104001", 1)[0],  # fewer rows than max_matches
    ],
)
def test_a_schedule_with_anything_the_client_does_not_know_is_refused(c1, tmp_path, schedule):
    (c1.parent / "schedule.csv").write_text(schedule, encoding="utf-8")

    with pytest.raises(PlanRefused):
        StageRunner(c1, tmp_path / "out", c1_arena(c1))


def test_a_dry_run_needs_no_approval_and_never_posts(tmp_path):
    # The W2 plan as it is on main: no execution approval recorded.
    arena = arena_for(PLAN)

    report = StageRunner(PLAN, tmp_path / "out", arena, dry_run=True, say=lambda m: None).run()

    assert len(report) == 8 and all(row["ok"] for row in report)
    assert all(row["cap_micro_eur"] == 400_000 and row["estimate_micro_eur"] for row in report)
    assert arena.posts() == []
    assert json.loads((tmp_path / "out/dry-run.json").read_text()) == report


def test_a_match_billed_far_above_its_estimate_holds_as_a_cost_jump(approved, tmp_path):
    plan = yaml.safe_load(approved.read_text(encoding="utf-8"))
    plan["budget"]["cost_jump_factor"] = 2.0
    approved.write_text(yaml.safe_dump(plan, sort_keys=False), encoding="utf-8")
    arena = arena_for(approved, estimate=100_000, cost=300_000)  # 3 x its quote

    with pytest.raises(RunStopped, match="cost jump"):
        client(approved, tmp_path / "out", arena).run()

    assert len(arena.posts()) == 1
    within = arena_for(approved, estimate=100_000, cost=190_000)  # under 2 x: plays on
    assert len(client(approved, tmp_path / "other", within).run()) == 8


def test_a_match_that_never_ends_holds_after_the_maximum_wait(approved, tmp_path):
    arena = arena_for(approved, status="running")
    ticks = iter(range(0, 10_000, 600))  # each poll is ten minutes later

    runner = client(approved, tmp_path / "out", arena, max_wait=3600, clock=lambda: next(ticks))
    with pytest.raises(RunStopped, match="still running after 3600 s"):
        runner.run()

    (attempt,) = runner.attempts().values()
    assert attempt["state"] == "started" and len(arena.posts()) == 1  # never posted again


def test_every_seats_fallback_share_and_the_arenas_setup_are_recorded(approved, tmp_path):
    arena = arena_for(approved)
    runner = client(approved, tmp_path / "out", arena)

    runner.run()

    first = sorted(runner.attempts().values(), key=lambda a: a["order"])[0]
    assert sorted(first["fallback_shares"]) == [f"p{i}" for i in range(1, 9)]
    assert first["arena_setup"]["caps"] == {"match_eur": 0.5, "month_eur": 25}


def test_a_paid_run_needs_the_pre_start_report_and_the_arena_build(approved, tmp_path):
    arena = arena_for(approved)

    with pytest.raises(PlanRefused, match="--pre-start-report, --arena-build"):
        client(approved, tmp_path / "out", arena, evidence={}).run()
    assert arena.posts() == []


def test_the_estimate_comes_before_every_start_and_a_dry_run_sends_no_confirm_spend(
    approved, tmp_path
):
    arena = arena_for(approved)
    client(approved, tmp_path / "out", arena).run()
    paths = [path for method, path, _ in arena.calls if method == "POST"]
    assert paths == ["/matches/estimate", "/matches"] * 8  # a fresh quote before each start

    dry = arena_for(approved)
    client(approved, tmp_path / "dry", dry, dry_run=True).run()
    assert not any(body and body.get("confirm_spend") for _, _, body in dry.calls)
    assert all(path != "/matches" for method, path, _ in dry.calls if method == "POST")


def test_spend_comes_from_the_arenas_batch_history_so_a_new_folder_resets_nothing(
    approved, tmp_path
):
    arena = arena_for(approved, cost=390_000, estimate=200_000)
    with pytest.raises(RunStopped):
        client(approved, tmp_path / "first", arena).run()
    assert len(arena.posts()) == 7

    # The same arena seen from a fresh out folder: its seven matches are foreign there.
    with pytest.raises(RunStopped, match="in no attempt of this out folder"):
        client(approved, tmp_path / "fresh", arena).run()
    assert len(arena.posts()) == 7


def test_two_matches_for_one_table_in_the_batch_hold(approved, tmp_path):
    arena = arena_for(approved)
    runner = client(approved, tmp_path / "out", arena)
    for attempt_id in ("a1", "a2"):
        status, record = arena("POST", "/matches", runner.body(runner.matches[0], attempt_id))
        runner._write(
            {
                "attempt_id": attempt_id,
                "order": 1,
                "state": "ended",
                "match_id": record["id"],
                "cost_micro_eur": 1,
            }
        )

    with pytest.raises(RunStopped, match="two matches for one table"):
        runner.gates(runner.matches[1])


def test_a_stage_waits_for_the_other_stages_released_checkpoint(approved, tmp_path):
    plan = yaml.safe_load(approved.read_text(encoding="utf-8"))
    plan["requires_release_from"] = "C1-out"
    approved.write_text(yaml.safe_dump(plan, sort_keys=False), encoding="utf-8")
    arena = arena_for(approved)
    out = tmp_path / "W2-out"

    with pytest.raises(RunStopped, match="waits for the reviewed checkpoint"):
        client(approved, out, arena).run()
    assert arena.posts() == []
    (tmp_path / "C1-out").mkdir()
    (tmp_path / "C1-out/checkpoint.jsonl").write_text(
        json.dumps({"released_after": 1, "evidence": "review (test)"}) + "\n"
    )
    assert len(client(approved, out, arena).run()) == 8


def test_a_stricter_reserve_may_be_set_but_never_one_below_the_limit(approved, tmp_path):
    plan = yaml.safe_load(approved.read_text(encoding="utf-8"))
    plan["budget"]["reserve_eur"] = 0.5
    approved.write_text(yaml.safe_dump(plan, sort_keys=False), encoding="utf-8")
    assert client(approved, tmp_path / "a", arena_for(approved)).reserve == 500_000
    plan["budget"]["reserve_eur"] = 0.3
    approved.write_text(yaml.safe_dump(plan, sort_keys=False), encoding="utf-8")
    with pytest.raises(PlanRefused, match="reserve_eur"):
        client(approved, tmp_path / "b", arena_for(approved))


def job_csv(rows):
    head = "order,game,models,seed,settings,memory,estimate_micro_eur\n"
    return head + "".join(rows)


def job_row(order, models, settings, seed=2104001, game="civ", memory="false"):
    quoted = lambda v: '"' + json.dumps(v).replace('"', '""') + '"'  # noqa: E731
    return f"{order},{game},{quoted(models)},{seed},{quoted(settings)},{memory},60000\n"


@pytest.fixture
def c1_job(c1):
    plan = yaml.safe_load(c1.read_text(encoding="utf-8"))
    roster = ["glm-flash", "deepseek-flash", "gpt-luna", "claude-haiku"]
    rotations = [roster[i:] + roster[:i] for i in range(4)]
    body = job_csv(job_row(i + 1, r, plan["settings"]) for i, r in enumerate(rotations))
    (c1.parent / "schedule.csv").write_text(body, encoding="utf-8", newline="")
    plan.update(seed=2104001, models=roster)
    plan["schedule_sha256"] = __import__("hashlib").sha256(body.encode()).hexdigest()
    c1.write_text(yaml.safe_dump(plan, sort_keys=False), encoding="utf-8")
    return c1


def test_the_job_form_csv_plays_its_rows_as_frozen(c1_job, tmp_path):
    arena = c1_arena(c1_job)

    with pytest.raises(RunStopped, match="review checkpoint"):
        client(c1_job, tmp_path / "out", arena).run()

    (body,) = arena.posts()
    assert body["models"] == ["glm-flash", "deepseek-flash", "gpt-luna", "claude-haiku"]
    assert body["seed"] == 2104001 and body["settings"]["rounds"] == 20


@pytest.mark.parametrize(
    ("change", "says"),
    [
        (lambda t: t.replace("1,civ,", "1,poker,", 1), "game poker"),
        (lambda t: t.replace("2104001", "2104002", 1), "seed"),
        (lambda t: t.replace('""rounds"": 20', '""rounds"": 60', 1), "frozen"),
        (lambda t: t.replace(",false,", ",true,", 1), "memory"),
        (lambda t: t.replace("glm-flash", "qwen-flash", 1), "roster"),
    ],
)
def test_a_job_form_row_that_differs_from_the_frozen_plan_is_refused(
    c1_job, tmp_path, change, says
):
    schedule = c1_job.parent / "schedule.csv"
    changed = change(schedule.read_text(encoding="utf-8"))
    schedule.write_text(changed, encoding="utf-8", newline="")
    plan = yaml.safe_load(c1_job.read_text(encoding="utf-8"))
    plan["schedule_sha256"] = __import__("hashlib").sha256(changed.encode()).hexdigest()
    c1_job.write_text(yaml.safe_dump(plan, sort_keys=False), encoding="utf-8")

    with pytest.raises(PlanRefused, match=says):
        StageRunner(c1_job, tmp_path / "out", c1_arena(c1_job))


def test_a_job_form_csv_must_match_its_pinned_bytes(c1_job, tmp_path):
    schedule = c1_job.parent / "schedule.csv"
    schedule.write_text(schedule.read_text(encoding="utf-8") + "\n", encoding="utf-8", newline="")

    with pytest.raises(PlanRefused, match="pins"):
        StageRunner(c1_job, tmp_path / "out", c1_arena(c1_job))


def test_run_json_records_hashes_evidence_counts_and_stop_reasons(c1, tmp_path):
    out = tmp_path / "out"
    with pytest.raises(RunStopped):
        client(c1, out, c1_arena(c1)).run()

    summary = json.loads((out / "run.json").read_text())
    assert len(summary["client_sha256"]) == 64 and summary["plan_sha256"]
    assert summary["pre_start_report"] == EVIDENCE["pre_start_report"]
    assert summary["arena_build"] == EVIDENCE["arena_build"]
    assert "operator-supplied" in summary["arena_build_provenance"]
    (attempt,) = summary["attempts"]
    assert attempt["body"]["settings"]["match_budget_eur"] == 0.2
    assert attempt["estimate_micro_eur"] == 60_000 and attempt["cap_micro_eur"] == 200_000
    assert set(attempt["seat_counts"]["p1"]) == {
        "model",
        "decisions",
        "fallbacks",
        "rejected",
        "agent_failed",
    }


def test_a_job_form_csv_without_a_pinned_hash_is_refused(c1_job, tmp_path):
    plan = yaml.safe_load(c1_job.read_text(encoding="utf-8"))
    del plan["schedule_sha256"]
    c1_job.write_text(yaml.safe_dump(plan, sort_keys=False), encoding="utf-8")

    with pytest.raises(PlanRefused, match="must be pinned"):
        StageRunner(c1_job, tmp_path / "out", c1_arena(c1_job))


def test_one_stage_client_at_a_time_and_the_lock_is_released_after(approved, tmp_path):
    out = tmp_path / "out"
    lock = tmp_path / ".stage-runner.lock"
    lock.write_text("C1 pid 1 since earlier\n")
    arena = arena_for(approved)

    with pytest.raises(RunStopped, match="another stage client holds"):
        client(approved, out, arena).run()
    assert arena.posts() == []

    lock.unlink()
    client(approved, out, arena).run()
    assert not lock.exists() and len(arena.posts()) == 8


def test_a_resume_with_a_changed_plan_is_refused(c1, tmp_path):
    out = tmp_path / "out"
    with pytest.raises(RunStopped, match="review checkpoint"):
        client(c1, out, c1_arena(c1)).run()
    c1.write_text(c1.read_text(encoding="utf-8") + "# changed\n", encoding="utf-8")

    with pytest.raises(PlanRefused, match="another plan or schedule"):
        client(c1, out, c1_arena(c1)).run()


@pytest.mark.parametrize(
    ("override", "says"),
    [
        ({"paused": True}, "paused"),
        ({"agent_failed": True}, "agent failed"),
    ],
)
def test_a_running_match_that_pauses_or_loses_an_agent_holds_at_once(
    approved, tmp_path, override, says
):
    arena = arena_for(approved, status="running", **override)
    ticks = iter(range(0, 100_000, 600))  # without the watch: "still running" after an hour

    with pytest.raises(RunStopped, match=says):
        client(approved, tmp_path / "out", arena, max_wait=3600, clock=lambda: next(ticks)).run()

    assert len(arena.posts()) == 1  # nothing more started, the match is not aborted
    assert not any(path.endswith("/abort") for _, path, _ in arena.calls)
