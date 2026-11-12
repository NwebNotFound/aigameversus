"""The W2 guest-stage client against a fake arena: no server, no model, nothing spent."""

import json
import shutil
from pathlib import Path

import pytest
import yaml

from arena.research.guest_runner import GuestRunner, PlanRefused
from arena.research.runner import RunStopped

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
        self.cost = override.get("cost", 200_000)
        self.running = override.get("running", [])
        self.prices = {g["id"]: dict(g) for g in plan["guests"]}
        self.status = override.get("status", "finished")
        self.guest_turns = override.get("guest_turns", (10, 0))  # accepted, fallback
        self.role = override.get("role")  # None: the planned one
        self.agent_failed = override.get("agent_failed", False)
        self.lose_post = 0  # POSTs that raise after creating (1) or without creating (2)

    def __call__(self, method, path, body):
        self.calls.append((method, path, body))
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
            guest = seat["guest_seat"]
            role = self.role or seat["expected_role"]
            accepted, fallback = self.guest_turns
            events = [{"type": "role_assigned", "data": {"player": guest, "role": role}}]
            events += [{"type": "action_accepted", "data": {"player": guest}}] * accepted
            events += [{"type": "action_fallback", "data": {"player": guest}}] * fallback
            if self.agent_failed:
                events.append({"type": "agent_failed", "data": {"player": "p1"}})
            return 200, events
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


def client(plan_path, out, arena, **kwargs):
    runner = GuestRunner(
        plan_path, out, arena, poll=0, sleep=lambda s: None, say=lambda m: None, **kwargs
    )
    arena.rows = runner.matches
    return runner


def arena_for(plan_path, **override):
    return FakeArena(yaml.safe_load(plan_path.read_text(encoding="utf-8")), **override)


def test_the_plan_on_main_may_not_start_without_its_execution_approval(tmp_path):
    with pytest.raises(PlanRefused, match="execution approval"):
        GuestRunner(PLAN, tmp_path / "out", arena_for(PLAN))


def test_a_schedule_that_is_not_the_plans_own_is_refused(approved, tmp_path):
    csv = approved.parent / "schedule.csv"
    lines = csv.read_text(encoding="utf-8").splitlines()
    lines[1], lines[2] = lines[2], lines[1]  # two rows swapped
    csv.write_text("\n".join(lines) + "\n", encoding="utf-8")

    with pytest.raises(PlanRefused, match="not the schedule"):
        GuestRunner(approved, tmp_path / "out", arena_for(approved))


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


def test_the_full_cap_is_held_for_the_next_match_and_a_lost_start_counts_at_the_cap(
    approved, tmp_path
):
    runner = client(approved, tmp_path / "out", arena_for(approved))
    for order in range(1, 8):
        runner._write(
            {"attempt_id": f"a{order}", "order": order, "state": "ended", "cost_micro_eur": 390_000}
        )
    runner._write({"attempt_id": "x", "order": 99, "state": "started", "match_id": "lost"})
    # 7 x 0.39 + the lost start at the cap 0.40 = 3.13 EUR: 3 x a tiny quote still fits 90 %
    # (3.133 <= 3.15), but the next match's full cap would pass 3.50 (3.53).
    arena = arena_for(approved, estimate=1_000)

    with pytest.raises(RunStopped, match="full cap"):
        client(approved, tmp_path / "out", arena).gates(runner.matches[7])
    assert arena.posts() == []


@pytest.mark.parametrize(
    ("override", "says"),
    [
        ({"status": "interrupted"}, "match interrupted"),
        ({"agent_failed": True}, "a failed agent"),
        ({"guest_turns": (8, 2)}, "guest fallback share 20%"),
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


def test_a_post_that_started_nothing_holds_and_the_next_run_starts_it_once(approved, tmp_path):
    arena = arena_for(approved)
    arena.lose_post = 2  # no answer, and no match was created

    first = client(approved, tmp_path / "out", arena)
    with pytest.raises(RunStopped, match="run again later"):
        first.run()
    assert arena.matches == {}
    # Not yet decided: a slow start could still show, so this run never calls it unstarted.
    assert [a["state"] for a in first.attempts().values()] == ["starting"]

    arena.lose_post = 0
    ended = client(approved, tmp_path / "out", arena).run()
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
