"""No sockets/models: exercise the money/client boundary with a fake arena."""

import copy
import csv
import hashlib
import shutil
from pathlib import Path

import pytest
import yaml

from arena.research.runner import RunStopped
from arena.research.tables import Tables, load_job, lock, read_json, save, start_allowed

JOBS = Path(__file__).resolve().parents[2] / "research/TABLES"
EVIDENCE = dict(
    execute=True,
    review_evidence="reviewed merge",
    pre_start_report="PR comment",
    arena_build="fake-build",
)


class FakeArena:
    def __init__(self):
        self.records = []
        self.bodies = []
        self.quote = 60_000
        self.cost = 50_000
        self.month = 3_756_279
        self.events_extra = []
        self.ambiguous = False
        self.record_start = True
        self.status = "finished"
        self.cap_override = None
        self.pauses = []
        self.price_jump = False

    def __call__(self, method, path, body):
        if path == "/models/catalog":
            job = read_json(JOBS / "W2.json")
            return 200, {
                "fresh": True,
                "models": [
                    {"id": model, **{k: v + int(self.price_jump) for k, v in price.items()}}
                    for model, price in job["guest_price_ceilings"].items()
                ],
            }
        if path == "/matches/estimate":
            assert "confirm_spend" not in body
            return 200, {
                "estimate_micro_eur": self.quote,
                "cap_micro_eur": self.cap_override
                or round(body["settings"]["match_budget_eur"] * 1e6),
                "fits": True,
            }
        if path == "/matches" and method == "POST":
            assert body["confirm_spend"] is True
            assert set(body) == {
                "game",
                "models",
                "seed",
                "settings",
                "memory",
                "batch",
                "confirm_spend",
            }
            self.bodies.append(copy.deepcopy(body))
            record = {
                **copy.deepcopy(body),
                "id": str(len(self.bodies)),
                "status": self.status,
                "seats": {f"p{i}": {"model_id": m} for i, m in enumerate(body["models"], 1)},
            }
            if self.record_start:
                self.records.append(record)
            if self.ambiguous:
                raise OSError("POST response lost")
            return 201, record
        if path.startswith("/matches?batch="):
            return 200, [r for r in self.records if r["batch"]["id"] == path.split("=")[1]]
        if path == "/matches?status=running":
            return 200, [r for r in self.records if r["status"] == "running"]
        if path == "/ledger/month":
            return 200, {"spent_micro_eur": self.month}
        if path == "/setup":
            return 200, {"caps": {"match_eur": 0.50, "month_eur": 25}}
        if path.endswith("/cost"):
            return 200, {"total_micro_eur": self.cost}
        if path.endswith("/events"):
            record = next(r for r in self.records if r["id"] == path.split("/")[2])
            roles = []
            if record["batch"]["id"] == "W2":
                guest = next(p for p, s in record["seats"].items() if "/" in s["model_id"])
                roles = [
                    {
                        "type": "role_assigned",
                        "data": {
                            "player": guest,
                            "role": "werewolf" if record["batch"]["index"] <= 4 else "seer",
                        },
                    }
                ]
            return 200, [
                {"type": "match_started", "data": {"settings": record["settings"]}},
                *roles,
                *[{"type": "action_accepted", "data": {"player": p}} for p in record["seats"]],
                *self.events_extra,
            ]
        if path.endswith("/pause"):
            self.pauses.append(path)
            return 200, {"paused": True}
        raise AssertionError((method, path, body))


def client(tmp_path, api, stage="C1"):
    return Tables(
        approved_job(tmp_path, stage), tmp_path, api, sleep=lambda _: None, say=lambda _: None
    )


def approved_job(tmp_path, stage="C1"):
    folder = tmp_path / "fake-approved-jobs"
    folder.mkdir(parents=True, exist_ok=True)
    job = read_json(JOBS / f"{stage}.json")
    job.pop("reviewed_c1_outcome", None)
    job.update(execution_plan_approved=True, execution_approval_evidence="fake-test approval only")
    shutil.copy(JOBS / job["csv"], folder / job["csv"])
    path = folder / f"{stage}.json"
    save(path, job)
    return path


def test_reviewed_inputs_and_no_csv_tampering(tmp_path):
    for stage in ("C1", "W2"):
        job, rows = load_job(JOBS / f"{stage}.json")
        assert len(rows) == (4 if stage == "C1" else 8)
        assert job["approval"]
    job = read_json(JOBS / "C1.json")
    job["csv"] = "bad.csv"
    (tmp_path / "bad.csv").write_text("changed")
    save(tmp_path / "job.json", job)
    with pytest.raises(RunStopped, match="hash"):
        load_job(tmp_path / "job.json")


def test_explicit_jobs_preserve_the_registered_seeds_rosters_and_order():
    root = JOBS.parents[1]
    c1 = yaml.safe_load((root / "research/C1/PLAN.yaml").read_text())
    _, c1_rows = load_job(JOBS / "C1.json")
    for index, row in enumerate(c1_rows):
        assert row["seed"] == c1["seed"]
        assert row["models"] == c1["models"][index:] + c1["models"][:index]
    with (root / "research/W2/schedule.csv").open(newline="") as stream:
        registered = list(csv.DictReader(stream))
    _, w2_rows = load_job(JOBS / "W2.json")
    for row, original in zip(w2_rows, registered, strict=True):
        assert row["order"] == int(original["order"])
        assert row["seed"] == int(original["seed"])
        assert row["models"] == [original[f"p{i}"] for i in range(1, 9)]


def test_dry_run_never_posts_a_match(tmp_path):
    api = FakeArena()
    assert client(tmp_path, api).run() == "dry-run"
    assert not api.bodies
    assert read_json(tmp_path / "C1/dry-run.json")["paid_starts"] == 0


@pytest.mark.parametrize("missing", ["review_evidence", "pre_start_report", "arena_build"])
def test_live_requires_review_report_and_build(tmp_path, missing):
    kwargs = EVIDENCE.copy()
    kwargs[missing] = None
    api = FakeArena()
    with pytest.raises(RunStopped, match="Execution requires"):
        client(tmp_path, api).run(**kwargs)
    assert not api.bodies


def test_first_smoke_holds_and_restart_or_new_folder_cannot_duplicate(tmp_path):
    api = FakeArena()
    for root in (tmp_path, tmp_path, tmp_path / "different-output"):
        with pytest.raises(RunStopped, match="review/release"):
            client(root, api).run(**EVIDENCE)
    assert len(api.bodies) == 1
    state = read_json(tmp_path / "C1/run.json")
    assert state["intents"]["1"]["effective_limit_micro_eur"] == 200_000


def release(root):
    path = root / "C1/001.json"
    report = read_json(path)["report"]
    save(
        root / "C1/smoke-release.json",
        {
            "match_id": report["match_id"],
            "report_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "evidence": "Researcher review PR link",
        },
    )


def test_smoke_release_allows_remaining_three_once(tmp_path):
    api = FakeArena()
    with pytest.raises(RunStopped):
        client(tmp_path, api).run(**EVIDENCE)
    release(tmp_path)
    assert client(tmp_path, api).run(**EVIDENCE) == "finished"
    assert len(api.bodies) == 4
    assert client(tmp_path, api).run(**EVIDENCE) == "finished"
    assert len(api.bodies) == 4


@pytest.mark.parametrize("recorded", [True, False])
def test_ambiguous_start_never_reposts(tmp_path, recorded):
    api = FakeArena()
    api.ambiguous = True
    api.record_start = recorded
    with pytest.raises(OSError):
        client(tmp_path, api).run(**EVIDENCE)
    api.ambiguous = False
    with pytest.raises(RunStopped, match="review/release" if recorded else "Unresolved POST"):
        client(tmp_path, api).run(**EVIDENCE)
    assert len(api.bodies) == 1


@pytest.mark.parametrize(
    "event",
    [
        {"type": "agent_failed", "data": {"player": "p1"}},
        {"type": "action_fallback", "data": {"player": "p1"}},
    ],
)
def test_failure_or_fallback_holds_before_next_table(tmp_path, event):
    api = FakeArena()
    api.events_extra = [event]
    api.status = "running"
    with pytest.raises(RunStopped):
        client(tmp_path, api).run(**EVIDENCE)
    assert len(api.bodies) == 1 and api.pauses


def test_cost_smoke_failure_cannot_be_released(tmp_path):
    api = FakeArena()
    api.cost = 160_001
    with pytest.raises(RunStopped, match="cost jump"):
        client(tmp_path, api).run(**EVIDENCE)
    release(tmp_path)
    with pytest.raises(RunStopped):
        client(tmp_path, api).run(**EVIDENCE)
    assert len(api.bodies) == 1


@pytest.mark.parametrize(
    "spent,estimate,month,reason",
    [
        (810_000, 60_000, 0, "90%"),
        (810_000, 1, 0, "Full reservation"),
        (0, 400_000, 0, "strictly below"),
        (0, 60_000, 20_000_000, "Monthly"),
    ],
)
def test_reservation_boundaries(spent, estimate, month, reason):
    job, _ = load_job(JOBS / "C1.json")
    with pytest.raises(RunStopped, match=reason):
        start_allowed(spent, estimate, job, month)


@pytest.mark.parametrize("change", ["cap", "estimate", "month"])
def test_fresh_checks_block_any_post(tmp_path, change):
    api = FakeArena()
    if change == "cap":
        api.cap_override = 500_000
    if change == "estimate":
        api.quote = 400_000
    if change == "month":
        api.month = 20_000_000
    with pytest.raises(RunStopped):
        client(tmp_path, api).run(**EVIDENCE)
    assert not api.bodies


def test_server_costs_survive_missing_local_summary(tmp_path):
    api = FakeArena()
    with pytest.raises(RunStopped):
        client(tmp_path, api).run(**EVIDENCE)
    release(tmp_path)
    # A low estimate cannot override the full stage reservation of existing cost.
    api.cost = 810_000
    with pytest.raises(RunStopped):
        client(tmp_path, api).run(**EVIDENCE)
    assert len(api.bodies) == 1


def test_lock_refuses_concurrent_client(tmp_path):
    with lock(tmp_path), pytest.raises(RunStopped, match="lock"), lock(tmp_path):
        pass


def test_unrelated_running_match_holds_before_any_dispatch(tmp_path):
    api = FakeArena()
    api.records.append({"id": "unrelated", "status": "running", "batch": {"id": "foreign"}})
    with pytest.raises(RunStopped, match="Another match is running"):
        client(tmp_path, api).run(**EVIDENCE)
    assert not api.bodies


def test_w2_waits_for_reviewed_c1_smoke(tmp_path):
    api = FakeArena()
    with pytest.raises(RunStopped, match="review/release"):
        client(tmp_path, api, "W2").run(**EVIDENCE)
    assert not api.bodies


def test_guest_price_jump_blocks_even_estimates_only(tmp_path):
    api = FakeArena()
    api.price_jump = True
    with pytest.raises(RunStopped, match="price above"):
        client(tmp_path, api, "W2").run()
    assert not api.bodies


def test_both_stages_share_smoke_gate_then_complete_without_duplicate_posts(tmp_path):
    api = FakeArena()
    with pytest.raises(RunStopped):
        client(tmp_path, api).run(**EVIDENCE)
    release(tmp_path)
    assert client(tmp_path, api, "W2").run(**EVIDENCE) == "finished"
    assert len(api.bodies) == 9  # one C1 smoke plus eight W2 tables
    assert client(tmp_path, api, "W2").run(**EVIDENCE) == "finished"
    assert len(api.bodies) == 9
    assert client(tmp_path / "fresh-output", api, "W2").run(**EVIDENCE) == "finished"
    assert len(api.bodies) == 9  # Same server batch, no replay even without local journal.


def test_w2_reserves_only_its_enforced_table_limit():
    job, _ = load_job(JOBS / "W2.json")
    assert job["reservation_micro_eur"] == job["match_micro_eur"] == 400_000
    start_allowed(3_100_000, 1, job, 3_756_279)
    with pytest.raises(RunStopped, match="Full reservation"):
        start_allowed(3_100_001, 1, job, 3_756_279)


def test_never_ending_match_has_a_persisted_bounded_wait(tmp_path):
    api = FakeArena()
    api.status = "running"
    clock = [0]

    def advance(_):
        clock[0] += 2

    runner = Tables(
        approved_job(tmp_path),
        tmp_path,
        api,
        sleep=advance,
        say=lambda _: None,
        now=lambda: clock[0],
        max_wait_seconds=1,
    )
    with pytest.raises(RunStopped, match="deadline"):
        runner.run(**EVIDENCE)
    assert len(api.bodies) == 1 and api.pauses
    assert read_json(tmp_path / "C1/run.json")["intents"]["1"]["wait_deadline_epoch"] == 1


def test_published_jobs_are_dry_only_until_fresh_execution_approval(tmp_path):
    for stage in ("C1", "W2"):
        api = FakeArena()
        job_path = approved_job(tmp_path / stage, stage)
        job = read_json(job_path)
        job.update(execution_plan_approved=False, execution_approval_evidence=None)
        save(job_path, job)
        runner = Tables(job_path, tmp_path / stage, api)
        assert runner.run() == "dry-run"
        with pytest.raises(RunStopped, match="post-review execution approval"):
            runner.run(**EVIDENCE)
        assert not api.bodies


@pytest.mark.parametrize("change", ["duplicate", "gap", "roster", "settings"])
def test_server_history_cannot_introduce_unlisted_or_repeated_tables(tmp_path, change):
    api = FakeArena()
    with pytest.raises(RunStopped):
        client(tmp_path, api).run(**EVIDENCE)
    if change == "duplicate":
        api.records.append(copy.deepcopy(api.records[0]))
    elif change == "gap":
        api.records[0]["batch"]["index"] = 2
    elif change == "roster":
        api.records[0]["seats"]["p1"]["model_id"] = "unlisted-model"
    else:
        api.records[0]["settings"]["match_budget_eur"] = 0.50
    with pytest.raises(RunStopped):
        client(tmp_path, api).run(**EVIDENCE)
    assert len(api.bodies) == 1


@pytest.mark.parametrize("status", ["aborted", "finished", "failed", "interrupted"])
def test_w2_accepts_explicit_review_of_terminal_c1_outcome(tmp_path, status):
    api = FakeArena()
    api.records.append(
        {"id": "reviewed", "game": "civ", "seed": 2104001, "status": status, "batch": {"id": "C1"}}
    )
    runner = client(tmp_path, api, "W2")
    runner.job["reviewed_c1_outcome"] = {
        "match_id": "reviewed",
        "evidence": "Lead reviewed outcome",
    }
    assert runner.run(**EVIDENCE) == "finished"
    assert len(api.bodies) == 8


@pytest.mark.parametrize("case", ["missing", "running", "no_evidence"])
def test_reviewed_c1_outcome_requires_terminal_match_and_evidence(tmp_path, case):
    api = FakeArena()
    if case != "missing":
        api.records.append(
            {
                "id": "reviewed",
                "game": "civ",
                "seed": 2104001,
                "status": "running" if case == "running" else "aborted",
                "batch": {"id": "C1"},
            }
        )
    runner = client(tmp_path, api, "W2")
    runner.job["reviewed_c1_outcome"] = {
        "match_id": "reviewed",
        "evidence": "" if case == "no_evidence" else "Lead review",
    }
    with pytest.raises(RunStopped, match="C1 outcome"):
        runner.run(**EVIDENCE)
    assert not api.bodies
