"""Play an explicit research stage (a PLAN.yaml and its schedule.csv: W2, C1), one match at
a time, through the arena API, inside the stage's shared money rules.

    uv run python -m arena.research.stage_runner research/W2/PLAN.yaml --out runs/W2 \\
        --api http://127.0.0.1:8100 --confirm-spend
    uv run python -m arena.research.stage_runner research/C1/PLAN.yaml --out runs/C1 --dry-run

It plays the CSV's rows in order and changes nothing about them: no substitution, no
retry, no tuning. The CSV is the whole list: columns `order`, `seed`, `p1`..`pN` (the
models), optional `guest`, `guest_seat`, `expected_role`; any other column, a gap in the
order or a length other than `max_matches` is refused. A guest-pilot plan
(`schema: explicit_guest_pilot_v1`) must also match the schedule it generates
(arena/research/guest_schedule.py). Nothing starts unless the plan records its execution
approval (`execution_plan_approved: true` with `execution_approval_evidence`).
`--dry-run` runs every check and estimate of the open rows and spends nothing; it needs
no execution approval and never posts a match.

Before every start, all of these must hold, or it holds and reports (exit 3):
- the month spent (GET /ledger/month) is below `notify_and_hold_at_month_eur`;
- a fresh free estimate (POST /matches/estimate) is strictly below the match cap, and the
  arena reads the cap back as `match_budget_eur`;
- the stage's spend over every attempt so far, plus 3x that estimate, stays within
  `stop_start_share` of `stage_eur`; plus the table's own limit (`match_budget_eur`,
  which the arena enforces since #144: Lead 42080496) stays within the stage;
- no listed price of a guest has risen above the plan's (plans with `guests`);
- no other match is running on the arena (one research match at a time, across stages);
- the stage is not at its review checkpoint (`checkpoint_after`: after that many matches
  it holds until `--release-checkpoint EVIDENCE` is written to the attempts log).

After every match it holds on a failed, interrupted or aborted match, a failed agent, a
fallback share above 10 % (the guest's, or with no guest column every model's), a guest
not dealt its planned role (with `expected_role`), or a match that cost more than
`budget.max_cost_per_match_eur`, or more than `budget.cost_jump_factor` x the estimate it
started with (a cost jump); a match still running after `--max-wait` holds too.
`<out>/run.json` keeps the effective limit, the reserve
and every attempt's booked cost.

What it sends is whitelisted: game, seed, the models of the row, the plan's settings,
memory off, confirm_spend and a batch whose label carries the attempt id. Nothing else
from the plan (never `expected_roles`). Each attempt is written to `<out>/attempts.jsonl`
before its POST (fsynced); after a crash or a POST without an answer the next run adopts
the match its batch label shows. If none shows, it holds until a person has checked the
arena and marks the attempt with `--mark-unstarted ATTEMPT_ID EVIDENCE`: it never reposts.

The stage's spend comes from the arena's batch history plus every local attempt it does not
show yet (a new out folder cannot reset it; a match in the batch that no attempt knows
holds). A schedule may also be in the job form (`order,game,models,seed,settings,memory,
estimate_micro_eur`, pinned by `schedule_sha256`; every row equal to the frozen plan). A
paid run needs `--pre-start-report` and `--arena-build` (operator-supplied; the arena shows
no commit); a plan may wait for another stage's released checkpoint
(`requires_release_from`) and hold a stricter reserve (`budget.reserve_eur`). One client
runs at a time across stages (`<out>/../.stage-runner.lock`, or `lock_path`); a resume
with another plan or schedule hash is refused; while a match runs, a pause or a failed
agent holds at once (the match is not aborted: a person decides).
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
import time
import uuid
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml

from arena.research.guest_schedule import rows
from arena.research.runner import ENDED, MICRO, Request, RunStopped, http_request, seat_reports

SENT_SETTINGS = (  # the settings a stage may send; nothing else of the plan is sent
    "template",
    "language",
    "prompt_version",
    "answer_repair",
    "match_budget_eur",
    "rounds",
    "strategy_text",
    "private_plan",
)
COLUMNS = {"order", "seed", "guest", "guest_seat", "expected_role"}  # besides p1..pN
# The self-describing job form of a schedule (Researcher's spec on #165): one table per row.
JOB_COLUMNS = ["order", "game", "models", "seed", "settings", "memory", "estimate_micro_eur"]
GUEST_SCHEMA = "explicit_guest_pilot_v1"
FALLBACK_LIMIT = 0.10
HOLD_STATUSES = {"failed", "interrupted", "aborted"}


class PlanRefused(Exception):
    """The plan or schedule may not be run as it is; nothing was started."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _micro(euros: Any) -> int:
    return int(Decimal(str(euros)) * MICRO)


class StageRunner:
    def __init__(
        self,
        plan_path: Path,
        out: Path,
        request: Request,
        *,
        poll: float = 10,
        sleep: Callable[[float], None] = time.sleep,
        say: Callable[[str], None] = print,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
        resume_after_hold: bool = False,
        dry_run: bool = False,
        max_wait: float = 4 * 3600,
        clock: Callable[[], float] = time.monotonic,
        evidence: Mapping[str, str] | None = None,
    ):
        self.clock = clock
        # Operator-supplied, recorded in run.json, required for a paid run: the written
        # pre-start report and the arena build (the arena exposes no commit to check it).
        self.evidence = dict(evidence or {})
        self.dry_run = dry_run  # every check and estimate, no POST /matches
        self.resume_after_hold = resume_after_hold  # a person decided to go on after a hold
        self.plan_path = plan_path
        self.plan = yaml.safe_load(plan_path.read_text(encoding="utf-8"))
        self.schedule_path = plan_path.parent / self.plan["schedule"]
        self.out = out
        self.request = request
        self.poll = poll
        self.sleep = sleep
        self.say = say
        self.now = now
        budget = self.plan["budget"]
        self.stage = _micro(budget["stage_eur"])
        self.cap = _micro(budget["match_cap_eur"])
        # The reserve of a new match, and of a start whose cost is not known: the table's own
        # enforced limit, settings.match_budget_eur (Lead 42080496, superseding 5c29a3f0).
        self.reserve = self.cap
        if "reserve_eur" in budget:  # a stage may hold more than its limit, never less
            if _micro(budget["reserve_eur"]) < self.cap:
                raise PlanRefused("budget.reserve_eur may not be below budget.match_cap_eur")
            self.reserve = _micro(budget["reserve_eur"])
        self.stop_share = Decimal(str(budget["stop_start_share"]))
        self.month_hold = _micro(budget["notify_and_hold_at_month_eur"])
        cost_stop = budget.get("max_cost_per_match_eur")
        self.cost_stop = None if cost_stop is None else _micro(cost_stop)
        self.checkpoint = self.plan.get("checkpoint_after")
        # Hold when a match is billed more than this many times the estimate it started with.
        jump = budget.get("cost_jump_factor")
        self.cost_jump = None if jump is None else Decimal(str(jump))
        self.max_wait = max_wait  # seconds a match may run before the client holds
        self.batch_id = str(self.plan["id"])
        # Another stage's out folder whose review checkpoint must be released first.
        self.after = self.plan.get("requires_release_from")
        # One client at a time across stages: a lock file beside the stages' out folders.
        lock = self.plan.get("lock_path")
        self.lock_path = Path(lock) if lock else out.parent / ".stage-runner.lock"
        self.matches = self._checked_schedule()

    # --- the plan ----------------------------------------------------------------------

    def _checked_schedule(self) -> list[dict[str, Any]]:
        plan = self.plan
        if not self.dry_run and (
            plan.get("execution_plan_approved") is not True
            or not plan.get("execution_approval_evidence")
        ):
            raise PlanRefused(
                "the plan records no execution approval (execution_plan_approved: true and "
                "execution_approval_evidence): nothing may start"
            )
        settings = plan["settings"]
        if set(settings) - set(SENT_SETTINGS):
            raise PlanRefused(
                f"settings outside the whitelist: {set(settings) - set(SENT_SETTINGS)}"
            )
        if _micro(settings.get("match_budget_eur", 0)) != self.cap:
            raise PlanRefused("settings.match_budget_eur must equal budget.match_cap_eur")
        if plan.get("memory") is not False or plan["budget"].get("automatic_retries") != 0:
            raise PlanRefused("the plan must play with memory off and no automatic retries")
        pinned = plan.get("schedule_sha256")
        if pinned and pinned != _sha256(self.schedule_path):
            raise PlanRefused("the schedule's bytes are not the ones the plan pins")
        with self.schedule_path.open(encoding="utf-8", newline="") as file:
            reader = csv.DictReader(file)
            listed = list(reader)
            columns = list(reader.fieldnames or [])
        if len(set(columns)) != len(columns):
            raise PlanRefused("the schedule has a column twice")
        if columns == JOB_COLUMNS:
            if not pinned:
                raise PlanRefused("a job-form schedule must be pinned by plan.schedule_sha256")
            listed = self._job_rows(listed)
            columns = ["order", "seed", *[k for k in listed[0] if k[:1] == "p"]] if listed else []
        seats = sorted(
            (c for c in columns if c[:1] == "p" and c[1:].isdigit()), key=lambda c: int(c[1:])
        )
        if not seats or seats != [f"p{i}" for i in range(1, len(seats) + 1)]:
            raise PlanRefused("the schedule needs seat columns p1..pN")
        if unknown := set(columns) - COLUMNS - set(seats) - {"quoted_micro_eur"}:
            raise PlanRefused(f"columns the client does not know: {sorted(unknown)}")
        if [row.get("order") for row in listed] != [str(i) for i in range(1, len(listed) + 1)]:
            raise PlanRefused("the order column must run 1, 2, 3, ... without gaps")
        if len(listed) != plan["max_matches"]:
            raise PlanRefused("the schedule's length is not max_matches")
        if plan.get("schema") == GUEST_SCHEMA:
            expected = [{k: str(v) for k, v in row.items()} for row in rows(plan)]
            if listed != expected:
                raise PlanRefused(f"{self.schedule_path} is not the schedule the plan generates")
        if len({row["order"] for row in listed}) != len(listed):
            raise PlanRefused("a table is listed twice")
        self.seats = seats
        return listed

    def _job_rows(self, listed: list[dict[str, str]]) -> list[dict[str, Any]]:
        """The job form's rows, each checked against the frozen plan, as seat rows."""
        plan, rows_ = self.plan, []
        width = None
        for row in listed:
            try:
                models = json.loads(row["models"])
                settings = json.loads(row["settings"])
                memory = json.loads(row["memory"])
                quote = int(row["estimate_micro_eur"])
                seed = int(row["seed"])
            except (ValueError, TypeError) as bad:
                raise PlanRefused(f"row {row.get('order')}: unreadable ({bad})") from None
            if row["game"] != plan["game"]:
                raise PlanRefused(f"row {row['order']}: game {row['game']} is not the plan's")
            if settings != plan["settings"]:
                raise PlanRefused(f"row {row['order']}: settings are not the plan's frozen ones")
            if memory is not False:
                raise PlanRefused(f"row {row['order']}: memory must be off")
            if "seed" in plan and seed != plan["seed"]:
                raise PlanRefused(f"row {row['order']}: seed {seed} is not the plan's")
            if not isinstance(models, list) or not all(isinstance(m, str) for m in models):
                raise PlanRefused(f"row {row['order']}: models must be a list of ids")
            if "models" in plan and sorted(models) != sorted(plan["models"]):
                raise PlanRefused(f"row {row['order']}: the roster is not the plan's")
            if width not in (None, len(models)):
                raise PlanRefused("every table must seat the same number of models")
            width = len(models)
            rows_.append(
                {
                    "order": row["order"],
                    "seed": str(seed),
                    **{f"p{i}": m for i, m in enumerate(models, start=1)},
                    "quoted_micro_eur": quote,
                }
            )
        return rows_

    def body(self, row: Mapping[str, str], attempt_id: str) -> dict[str, Any]:
        """Exactly what is sent for a row: nothing from the plan beyond the whitelist."""
        settings = {
            k: self.plan["settings"][k] for k in SENT_SETTINGS if k in self.plan["settings"]
        }
        return {
            "game": self.plan["game"],
            "seed": int(row["seed"]),
            "models": [row[seat] for seat in self.seats],
            "settings": settings,
            "memory": False,
            "confirm_spend": True,
            "batch": {
                "id": self.batch_id,
                "label": f"{self.batch_id} row {row['order']} attempt {attempt_id}",
                "index": int(row["order"]),
                "of": len(self.matches),
                "budget_eur": float(self.plan["budget"]["stage_eur"]),
            },
        }

    # --- the attempts log ----------------------------------------------------------------

    @property
    def attempts_path(self) -> Path:
        return self.out / "attempts.jsonl"

    def _write(self, line: dict[str, Any]) -> None:
        self.out.mkdir(parents=True, exist_ok=True)
        with self.attempts_path.open("a", encoding="utf-8", newline="\n") as log:
            log.write(json.dumps(line, ensure_ascii=False) + "\n")
            log.flush()
            os.fsync(log.fileno())  # on disk before the POST it announces

    def attempts(self) -> dict[str, dict[str, Any]]:
        """attempt id -> its lines merged, oldest first."""
        merged: dict[str, dict[str, Any]] = {}
        if self.attempts_path.exists():
            for raw in self.attempts_path.read_text(encoding="utf-8").splitlines():
                line = json.loads(raw)
                merged.setdefault(line["attempt_id"], {}).update(line)
        return merged

    def spent(self) -> int:
        """The stage's spend over every attempt: the ledger cost of each ended match, the
        full cap for one whose cost is not known (running, or a start that may have happened)."""
        total = 0
        for attempt in self.attempts().values():
            if attempt.get("state") == "not_started":
                continue
            cost = attempt.get("cost_micro_eur")
            total += self.reserve if cost is None else cost
        return total

    def stage_spent(self) -> int:
        """The stage's spend from the arena's own batch history (so a new output folder or a
        lost log cannot reset it), plus every local attempt the arena does not show yet: its
        known cost, or the reserve. A match in the batch that no attempt knows holds."""
        matches = self._get(f"/matches?batch={self.batch_id}")
        local = self.attempts()
        known = {a["match_id"] for a in local.values() if a.get("match_id")}
        indexes = [((m.get("batch") or {}).get("index")) for m in matches]
        if len(indexes) != len(set(indexes)):
            raise RunStopped("the batch holds two matches for one table: reconcile by hand")
        if foreign := [m["id"] for m in matches if m["id"] not in known]:
            raise RunStopped(
                f"match(es) {', '.join(foreign)} in batch {self.batch_id} are in no attempt "
                "of this out folder: reconcile by hand (wrong folder, or a start not logged)"
            )
        total = sum(self._get(f"/matches/{m['id']}/cost")["total_micro_eur"] for m in matches)
        shown = {m["id"] for m in matches}
        for attempt in local.values():
            if attempt.get("state") == "not_started" or attempt.get("match_id") in shown:
                continue
            cost = attempt.get("cost_micro_eur")
            total += self.reserve if cost is None else cost
        return total

    # --- gates -----------------------------------------------------------------------------

    def _get(self, path: str) -> Any:
        status, answer = self.request("GET", path, None)
        if status != 200:
            raise RunStopped(f"GET {path} answered {status}: {answer}")
        return answer

    def gates(self, row: Mapping[str, str]) -> dict[str, Any]:
        """Every check before a start; RunStopped names the first that fails."""
        month = self._get("/ledger/month")
        if month["spent_micro_eur"] >= self.month_hold:
            raise RunStopped(
                f"the month has spent {month['spent_micro_eur'] / MICRO:.4f} EUR, at or above "
                f"the hold of {self.month_hold / MICRO:.2f} EUR"
            )
        running = self._get("/matches?status=running")
        if running:
            raise RunStopped(f"{len(running)} other match(es) running: serial only")
        models = [row[seat] for seat in self.seats]
        status, estimate = self.request(
            "POST",
            "/matches/estimate",
            {
                "game": self.plan["game"],
                "models": models,
                "settings": self.body(row, "-")["settings"],
            },
        )
        if status != 200:
            raise RunStopped(f"no free estimate ({status}): {estimate}")
        quote = estimate["estimate_micro_eur"]
        if estimate["cap_micro_eur"] != self.cap:
            raise RunStopped(
                f"the arena reads the match cap back as {estimate['cap_micro_eur']}, "
                f"not {self.cap}: match_budget_eur is not in force"
            )
        if quote >= self.cap:
            raise RunStopped(f"the estimate {quote / MICRO:.6f} EUR is not below the match cap")
        spent = self.stage_spent()
        if spent + 3 * quote > self.stage * self.stop_share:
            raise RunStopped(
                f"spent {spent / MICRO:.6f} + 3 x {quote / MICRO:.6f} EUR would pass "
                f"{self.stop_share:.0%} of the stage's {self.stage / MICRO:.2f} EUR"
            )
        if spent + self.reserve > self.stage:
            raise RunStopped(
                f"spent {spent / MICRO:.6f} + the reserve {self.reserve / MICRO:.2f} "
                f"EUR would pass the stage's {self.stage / MICRO:.2f} EUR"
            )
        if self.plan.get("guests") and row.get("guest"):
            self._prices(row["guest"])
        setup = self._get("/setup")  # the arena's caps and options, as recorded evidence
        return {
            "arena_setup": {
                k: setup.get(k) for k in ("caps", "model_seats", "answer_repair", "mixed_seats")
            },
            "month_spent_micro_eur": month["spent_micro_eur"],
            "estimate_micro_eur": quote,
            "cap_micro_eur": estimate["cap_micro_eur"],
            "reserve_micro_eur": self.reserve,
            "stage_spent_micro_eur": spent,
        }

    def _prices(self, guest: str) -> None:
        planned = next(g for g in self.plan["guests"] if g["id"] == guest)
        catalog = self._get("/models/catalog")
        entry = next((m for m in catalog.get("models", []) if m.get("id") == guest), None)
        if entry is None:
            raise RunStopped(f"{guest} is not in the catalog now: no substitution")
        for side in ("input_usd_per_mtok", "output_usd_per_mtok"):
            listed = entry.get(side)  # the listed price (unverified ones are booked x1.25)
            if listed is None or Decimal(str(listed)) > Decimal(str(planned[side])):
                raise RunStopped(f"{guest}: {side} is {listed}, above the plan's {planned[side]}")

    # --- reconciling ------------------------------------------------------------------------

    def _find(self, attempt_id: str) -> dict[str, Any] | None:
        matches = self._get(f"/matches?batch={self.batch_id}")
        return next(
            (m for m in matches if attempt_id in ((m.get("batch") or {}).get("label") or "")), None
        )

    def reconcile(self) -> None:
        """An attempt written before its POST without a match id: adopt the match its batch
        label shows. Not shown is no proof that none was created (it may show later), so
        the attempt stays undecided and the run holds until a person marks it."""
        for attempt_id, attempt in self.attempts().items():
            if attempt.get("match_id") or attempt.get("state") in ("not_started", "ended"):
                continue
            found = self._find(attempt_id)
            if found is not None:
                self._write({"attempt_id": attempt_id, "match_id": found["id"], "state": "started"})
                self.say(f"attempt {attempt_id} started match {found['id']}: adopted")

    def undecided(self) -> list[dict[str, Any]]:
        return [
            a
            for a in self.attempts().values()
            if a.get("state") == "starting" and not a.get("match_id")
        ]

    def mark_unstarted(self, attempt_id: str, evidence: str) -> None:
        """A person checked the arena and found no match for this attempt: it never started."""
        if not evidence.strip():
            raise PlanRefused("marking an attempt unstarted needs the evidence of the check")
        attempt = self.attempts().get(attempt_id)
        if attempt is None or attempt.get("match_id") or attempt.get("state") != "starting":
            raise PlanRefused(f"{attempt_id} is no undecided attempt")
        self._write(
            {"attempt_id": attempt_id, "state": "not_started", "manual": evidence, "at": self._at()}
        )

    # --- running ------------------------------------------------------------------------------

    def _at(self) -> str:
        return self.now().isoformat()

    # --- the review checkpoint and the run summary ----------------------------------------

    @property
    def checkpoint_path(self) -> Path:
        return self.out / "checkpoint.jsonl"

    def ended(self) -> list[dict[str, Any]]:
        return [a for a in self.attempts().values() if a.get("state") == "ended"]

    def released(self) -> int:
        """Up to how many ended matches a person has released the stage, by evidence."""
        if not self.checkpoint_path.exists():
            return 0
        lines = [
            json.loads(x) for x in self.checkpoint_path.read_text(encoding="utf-8").splitlines()
        ]
        return max((line["released_after"] for line in lines), default=0)

    def release_checkpoint(self, evidence: str) -> None:
        """Record that a person reviewed the stage at its checkpoint and lets it go on."""
        if not evidence.strip():
            raise PlanRefused("a release needs the review's evidence")
        self.out.mkdir(parents=True, exist_ok=True)
        with self.checkpoint_path.open("a", encoding="utf-8", newline="\n") as log:
            line = {"released_after": len(self.ended()), "evidence": evidence, "at": self._at()}
            log.write(json.dumps(line, ensure_ascii=False) + "\n")

    def _after_gate(self) -> None:
        """A stage that must wait for another's review checkpoint (W2 after the C1 smoke)."""
        if not self.after:
            return
        other = Path(self.after)
        other = other if other.is_absolute() else self.out.parent / other
        released = other / "checkpoint.jsonl"
        if not released.exists() or not released.read_text(encoding="utf-8").strip():
            raise RunStopped(
                f"this stage waits for the reviewed checkpoint of {other}: not released yet"
            )

    def _at_checkpoint(self) -> None:
        if self.checkpoint and len(self.ended()) >= self.checkpoint > self.released():
            raise RunStopped(
                f"review checkpoint after {self.checkpoint} match(es): hold for the "
                "Researcher's review; go on only with --release-checkpoint EVIDENCE"
            )

    def summary(self) -> dict[str, Any]:
        """run.json: the effective limit, the reserve and every attempt's booked cost."""
        attempts = sorted(
            self.attempts().values(), key=lambda a: (a.get("order", 0), a.get("at", ""))
        )
        return {
            "stage": self.plan["id"],
            "generated_at": self._at(),
            "plan_sha256": _sha256(self.plan_path),
            "schedule_sha256": _sha256(self.schedule_path),
            "client_sha256": _sha256(Path(__file__)),
            "execution_approval_evidence": self.plan.get("execution_approval_evidence"),
            "pre_start_report": self.evidence.get("pre_start_report"),
            "arena_build": self.evidence.get("arena_build"),
            "arena_build_provenance": "operator-supplied; the arena exposes no commit to check",
            "checkpoint_releases": (
                [json.loads(x) for x in self.checkpoint_path.read_text().splitlines()]
                if self.checkpoint_path.exists()
                else []
            ),
            "frozen_settings": self.plan["settings"],
            "match_budget_eur": self.plan["settings"].get("match_budget_eur"),
            "cap_read_back_micro_eur": next(
                (a["cap_micro_eur"] for a in reversed(attempts) if "cap_micro_eur" in a), None
            ),
            "reserve_micro_eur": self.reserve,
            "stage_eur": self.stage / MICRO,
            "stage_spent_micro_eur": self.spent(),
            "booked_micro_eur": sum(a.get("cost_micro_eur") or 0 for a in attempts),
            "checkpoint_after": self.checkpoint,
            "released_after": self.released(),
            "stop_reasons": [a["hold"] for a in attempts if a.get("hold")],
            "attempts": attempts,  # every line merged: body, quote, limit, month, counts
        }

    def write_summary(self) -> None:
        self.out.mkdir(parents=True, exist_ok=True)
        (self.out / "run.json").write_text(
            json.dumps(self.summary(), indent=1, ensure_ascii=False) + "\n",
            encoding="utf-8",
            newline="\n",
        )

    def dry(self) -> list[dict[str, Any]]:
        """Every open row's checks and fresh estimate, nothing posted or written but the
        report `<out>/dry-run.json`. A row that would hold says why."""
        tried = {a["order"] for a in self.attempts().values() if a.get("state") != "not_started"}
        report = []
        for row in self.matches:
            if int(row["order"]) in tried:
                continue
            try:
                report.append({"order": int(row["order"]), "ok": True, **self.gates(row)})
            except RunStopped as held:
                report.append({"order": int(row["order"]), "ok": False, "hold": str(held)})
        self.out.mkdir(parents=True, exist_ok=True)
        (self.out / "dry-run.json").write_text(
            json.dumps(report, indent=1) + "\n", encoding="utf-8", newline="\n"
        )
        return report

    def run(self) -> list[dict[str, Any]]:
        """Play the open rows in order, one at a time. RunStopped on any hold."""
        if self.dry_run:
            return self.dry()
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            handle = os.open(self.lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            held_by = self.lock_path.read_text(encoding="utf-8", errors="replace").strip()
            raise RunStopped(
                f"another stage client holds {self.lock_path} ({held_by}): one at a time; "
                "delete the file only after checking that no client runs"
            ) from None
        with os.fdopen(handle, "w", encoding="utf-8") as lock:
            lock.write(f"{self.batch_id} pid {os.getpid()} since {self._at()}\n")
        try:
            return self._run()
        finally:
            self.lock_path.unlink(missing_ok=True)

    def _run(self) -> list[dict[str, Any]]:
        missing = [k for k in ("pre_start_report", "arena_build") if not self.evidence.get(k)]
        if missing:
            raise PlanRefused(
                f"a paid run needs {', '.join('--' + k.replace('_', '-') for k in missing)}"
            )
        self.out.mkdir(parents=True, exist_ok=True)
        hashes = (_sha256(self.plan_path), _sha256(self.schedule_path))
        for attempt in self.attempts().values():
            recorded = (attempt.get("plan_sha256"), attempt.get("schedule_sha256"))
            if recorded != (None, None) and recorded != hashes:
                raise PlanRefused(
                    f"attempt {attempt['attempt_id']} ran with another plan or schedule: a "
                    "changed plan is a new stage with its own out folder, never a resume"
                )
        held = [a for a in self.attempts().values() if a.get("hold")]
        if held and not self.resume_after_hold:
            raise RunStopped(
                f"held after row {held[-1]['order']}: {held[-1]['hold']} (go on only with "
                "--resume-after-hold, after a person decided)"
            )
        self.reconcile()
        if undecided := self.undecided():
            raise RunStopped(
                f"attempt {undecided[0]['attempt_id']} (row {undecided[0]['order']}): its POST "
                "may have started a match the arena does not show: check the arena, then "
                "--mark-unstarted ATTEMPT_ID EVIDENCE if none exists"
            )
        attempts = self.attempts()
        for attempt in attempts.values():  # a match that ran when the client stopped
            if attempt.get("match_id") and attempt.get("state") != "ended":
                self._finish(attempt["attempt_id"], attempt)
        attempts = self.attempts()
        tried = {a["order"] for a in attempts.values() if a.get("state") != "not_started"}
        for row in self.matches:
            if int(row["order"]) in tried:
                continue  # played or tried once: never again (no retries)
            self._at_checkpoint()
            self._after_gate()
            checks = self.gates(row)
            attempt_id = uuid.uuid4().hex[:12]
            body = self.body(row, attempt_id)
            self._write(
                {
                    "attempt_id": attempt_id,
                    "order": int(row["order"]),
                    "guest": row.get("guest"),
                    "state": "starting",
                    "at": self._at(),
                    "plan_sha256": _sha256(self.plan_path),
                    "schedule_sha256": _sha256(self.schedule_path),
                    "body": body,
                    **checks,
                }
            )
            try:
                status, record = self.request("POST", "/matches", body)
            except Exception as error:  # noqa: BLE001 - no answer: did it start? reconcile
                self.say(f"POST for row {row['order']} gave no answer ({type(error).__name__})")
                self.reconcile()
                if not self.attempts()[attempt_id].get("match_id"):
                    raise RunStopped(
                        f"row {row['order']}: no answer to its POST and no match shown: check "
                        f"the arena, then --mark-unstarted {attempt_id} EVIDENCE if none exists"
                    ) from error
                record = {"id": self.attempts()[attempt_id]["match_id"]}
                status = 201
            if status != 201:
                self._write({"attempt_id": attempt_id, "state": "not_started", "refused": status})
                raise RunStopped(f"the arena refused row {row['order']} ({status}): {record}")
            self._write({"attempt_id": attempt_id, "match_id": record["id"], "state": "started"})
            self.say(
                f"row {row['order']} started as match {record['id']} "
                f"({row.get('guest') or 'no guest'})"
            )
            self._finish(attempt_id, self.attempts()[attempt_id])
        self.write_summary()
        return self.ended()

    def _watch(self, attempt_id: str, attempt: dict[str, Any], match_id: str) -> None:
        """While a match runs: a pause (a cap, or a person) or a failed agent holds now. The
        match is not aborted (a person decides that); a later run waits for it again."""
        status, control = self.request("GET", f"/matches/{match_id}/control", None)
        problem = None
        if status == 200 and isinstance(control, dict) and control.get("paused"):
            problem = "paused"
        else:
            events = self._get(f"/matches/{match_id}/events")
            failed = sorted(
                {
                    (e.get("data") or {}).get("player")
                    for e in events
                    if e.get("type") == "agent_failed"
                }
            )
            if failed:
                problem = f"agent failed ({', '.join(failed)}) while it runs"
        if problem:
            self._write({"attempt_id": attempt_id, "hold": f"match {match_id} {problem}"})
            self.write_summary()
            raise RunStopped(
                f"row {attempt['order']}: match {match_id} {problem}: hold and report "
                "(the match is not aborted; a person decides)"
            )

    def _finish(self, attempt_id: str, attempt: dict[str, Any]) -> None:
        match_id = attempt["match_id"]
        record = {"status": "running"}
        started = self.clock()
        while record["status"] not in ENDED:
            record = self._get(f"/matches/{match_id}")
            if record["status"] not in ENDED:
                self._watch(attempt_id, attempt, match_id)
                if self.clock() - started > self.max_wait:
                    raise RunStopped(
                        f"match {match_id} still {record['status']} after {self.max_wait:g} s: "
                        "hold; a later run waits for it again"
                    )
                self.sleep(self.poll)
        events = self._get(f"/matches/{match_id}/events")
        cost = self._get(f"/matches/{match_id}/cost")
        month = self._get("/ledger/month")
        (self.out / f"{int(attempt['order']):03d}-{attempt_id}.json").write_text(
            json.dumps({"record": record, "cost": cost, "events": events}, ensure_ascii=False)
            + "\n",
            encoding="utf-8",
            newline="\n",
        )
        row = next(r for r in self.matches if int(r["order"]) == int(attempt["order"]))
        reports = seat_reports(events, {seat: row[seat] for seat in self.seats})
        every = {
            seat: (reports[seat].fallbacks / reports[seat].turns if reports[seat].turns else 1.0)
            for seat in self.seats
        }
        watched = [row["guest_seat"]] if row.get("guest_seat") else list(self.seats)
        shares = {seat: every[seat] for seat in watched}
        share = max(shares.values())
        dealt = next(
            (
                e["data"].get("role")
                for e in events
                if e.get("type") == "role_assigned"
                and (e.get("data") or {}).get("player") == row.get("guest_seat")
            ),
            None,
        )
        self._write(
            {
                "attempt_id": attempt_id,
                "state": "ended",
                "status": record["status"],
                "cost_micro_eur": cost["total_micro_eur"],
                "month_spent_after_micro_eur": month["spent_micro_eur"],
                "prompt_version": record.get("prompt_version"),
                "settings_recorded": record.get("settings"),
                "fallback_shares": {seat: round(v, 4) for seat, v in every.items()},
                "seat_counts": {
                    seat: {
                        "model": row[seat],
                        "decisions": r.turns,
                        "fallbacks": r.fallbacks,
                        "rejected": r.rejected,
                        "agent_failed": r.agent_failed,
                    }
                    for seat, r in reports.items()
                },
                "guest_role": dealt,
                "agent_failed": sorted(p for p, r in reports.items() if r.agent_failed),
                "ended_at": self._at(),
            }
        )
        self.say(
            f"row {row['order']} {record['status']}, {cost['total_micro_eur'] / MICRO:.6f} EUR; "
            f"stage {self.spent() / MICRO:.6f} of {self.stage / MICRO:.2f} EUR"
        )
        holds = []
        if record["status"] in HOLD_STATUSES:
            holds.append(f"match {record['status']}")
        if any(r.agent_failed for r in reports.values()):
            holds.append("a failed agent")
        if share > FALLBACK_LIMIT:
            worst = max(shares, key=shares.get)
            holds.append(f"fallback share {share:.0%} ({worst}: {row[worst]})")
        if row.get("expected_role") and dealt != row["expected_role"]:
            holds.append(f"guest dealt {dealt}, planned {row['expected_role']}")
        quote = attempt.get("estimate_micro_eur")
        if (
            self.cost_jump is not None
            and quote
            and cost["total_micro_eur"] > self.cost_jump * quote
        ):
            holds.append(
                f"cost jump: {cost['total_micro_eur'] / MICRO:.6f} EUR is above "
                f"{self.cost_jump} x the estimate {quote / MICRO:.6f}"
            )
        if self.cost_stop is not None and cost["total_micro_eur"] > self.cost_stop:
            holds.append(
                f"cost {cost['total_micro_eur'] / MICRO:.6f} EUR above the stop of "
                f"{self.cost_stop / MICRO:.2f}"
            )
        if holds:
            reason = "; ".join(holds)
            self._write({"attempt_id": attempt_id, "hold": reason})
        self.write_summary()
        if holds:
            raise RunStopped(f"row {row['order']}: {reason}: hold and report")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m arena.research.stage_runner",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("plan", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--api", default="http://127.0.0.1:8100")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--confirm-spend", action="store_true", help="play: this spends money")
    mode.add_argument("--dry-run", action="store_true", help="checks and estimates only: free")
    mode.add_argument(
        "--release-checkpoint",
        metavar="EVIDENCE",
        help="record the review at the checkpoint (who, which message), then exit",
    )
    mode.add_argument(
        "--mark-unstarted",
        nargs=2,
        metavar=("ATTEMPT_ID", "EVIDENCE"),
        help="after checking the arena by hand: this attempt started no match, then exit",
    )
    parser.add_argument("--pre-start-report", help="where the written pre-start report is")
    parser.add_argument("--arena-build", help="the arena build in use, as the operator knows it")
    parser.add_argument("--poll", type=float, default=10)
    parser.add_argument(
        "--max-wait", type=float, default=4 * 3600, help="seconds a match may run before a hold"
    )
    parser.add_argument(
        "--resume-after-hold",
        action="store_true",
        help="go on after a hold, once a person has decided to (the held row is not replayed)",
    )
    args = parser.parse_args(argv)
    sys.stdout.reconfigure(errors="backslashreplace", line_buffering=True)
    try:
        runner = StageRunner(
            args.plan,
            args.out,
            http_request(args.api),
            poll=args.poll,
            resume_after_hold=args.resume_after_hold,
            dry_run=args.dry_run,
            max_wait=args.max_wait,
            evidence={
                "pre_start_report": args.pre_start_report or "",
                "arena_build": args.arena_build or "",
            },
        )
        if args.mark_unstarted:
            runner.mark_unstarted(*args.mark_unstarted)
            print(f"Marked {args.mark_unstarted[0]} unstarted")
            return 0
        if args.release_checkpoint:
            runner.release_checkpoint(args.release_checkpoint)
            print(f"Released after {len(runner.ended())} match(es)")
            return 0
        ended = runner.run()
    except PlanRefused as refused:
        print(f"Refused: {refused}", file=sys.stderr)
        return 2
    except RunStopped as stop:
        print(f"Held: {stop}")
        return 3
    if args.dry_run:
        print(json.dumps(ended, indent=1))
        return 0 if all(row["ok"] for row in ended) else 3
    print(f"Done: {len(ended)} matches, stage {runner.spent() / MICRO:.6f} EUR")
    return 0


if __name__ == "__main__":
    sys.exit(main())
