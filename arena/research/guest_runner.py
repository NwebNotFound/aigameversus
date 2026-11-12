"""Play an explicit guest-stage schedule (research/W2: PLAN.yaml + schedule.csv), one match
at a time, through the arena API, inside the stage's shared money rules.

    uv run python -m arena.research.guest_runner research/W2/PLAN.yaml --out runs/W2 \\
        --api http://127.0.0.1:8100 --confirm-spend

It plays the CSV's rows in order and changes nothing about them: no substitution, no
retry, no tuning. It refuses to start at all unless the plan records its execution
approval (`execution_plan_approved: true` with `execution_approval_evidence`) and the CSV
is exactly the schedule the plan generates (arena/research/guest_schedule.py).

Before every start, all of these must hold, or it holds and reports (exit 3):
- the month spent (GET /ledger/month) is below `notify_and_hold_at_month_eur`;
- a fresh free estimate (POST /matches/estimate) is strictly below the match cap, and the
  arena reads the cap back as `match_budget_eur`;
- the stage's spend over every attempt so far, plus 3x that estimate, stays within
  `stop_start_share` of `stage_eur`; plus the full match cap stays within `stage_eur`;
- no listed price of a guest has risen above the plan's;
- no other match is running on the arena.

After every match it holds on a failed, interrupted or aborted match, a failed agent, a
guest fallback share above 10 %, or a guest not dealt its planned role.

What it sends is whitelisted: game, seed, the models of the row, the plan's settings,
memory off, confirm_spend and a batch whose label carries the attempt id. Nothing else
from the plan (never `expected_roles`). Each attempt is written to `<out>/attempts.jsonl`
before its POST; after a crash or a POST without an answer the next run finds the match by
its batch label instead of starting a second one, or holds while it cannot tell.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
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

SENT_SETTINGS = ("template", "language", "prompt_version", "answer_repair", "match_budget_eur")
FALLBACK_LIMIT = 0.10
HOLD_STATUSES = {"failed", "interrupted", "aborted"}


class PlanRefused(Exception):
    """The plan or schedule may not be run as it is; nothing was started."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _micro(euros: Any) -> int:
    return int(Decimal(str(euros)) * MICRO)


class GuestRunner:
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
    ):
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
        self.stop_share = Decimal(str(budget["stop_start_share"]))
        self.month_hold = _micro(budget["notify_and_hold_at_month_eur"])
        self.batch_id = str(self.plan["id"])
        self.matches = self._checked_schedule()

    # --- the plan ----------------------------------------------------------------------

    def _checked_schedule(self) -> list[dict[str, Any]]:
        plan = self.plan
        if plan.get("execution_plan_approved") is not True or not plan.get(
            "execution_approval_evidence"
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
        with self.schedule_path.open(encoding="utf-8", newline="") as file:
            listed = list(csv.DictReader(file))
        expected = [{k: str(v) for k, v in row.items()} for row in rows(plan)]
        if listed != expected:
            raise PlanRefused(f"{self.schedule_path} is not the schedule the plan generates")
        if len(listed) != plan["max_matches"]:
            raise PlanRefused("the schedule's length is not max_matches")
        return listed

    def body(self, row: Mapping[str, str], attempt_id: str) -> dict[str, Any]:
        """Exactly what is sent for a row: nothing from the plan beyond the whitelist."""
        settings = {
            k: self.plan["settings"][k] for k in SENT_SETTINGS if k in self.plan["settings"]
        }
        return {
            "game": self.plan["game"],
            "seed": int(row["seed"]),
            "models": [row[f"p{i}"] for i in range(1, 9)],
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
            total += self.cap if cost is None else cost
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
        models = [row[f"p{i}"] for i in range(1, 9)]
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
        spent = self.spent()
        if spent + 3 * quote > self.stage * self.stop_share:
            raise RunStopped(
                f"spent {spent / MICRO:.6f} + 3 x {quote / MICRO:.6f} EUR would pass "
                f"{self.stop_share:.0%} of the stage's {self.stage / MICRO:.2f} EUR"
            )
        if spent + self.cap > self.stage:
            raise RunStopped(
                f"spent {spent / MICRO:.6f} + the full cap {self.cap / MICRO:.2f} EUR would "
                f"pass the stage's {self.stage / MICRO:.2f} EUR"
            )
        self._prices(row["guest"])
        return {
            "month_spent_micro_eur": month["spent_micro_eur"],
            "estimate_micro_eur": quote,
            "cap_micro_eur": estimate["cap_micro_eur"],
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

    def reconcile(self, *, settle_missing: bool = True) -> None:
        """An attempt written before its POST without a match id: find the match it may have
        started. Found: adopt it. Not found: it never started (only with `settle_missing`;
        right after a POST without an answer the client holds instead, and the next run
        decides, when a slow start would have shown)."""
        for attempt_id, attempt in self.attempts().items():
            if attempt.get("match_id") or attempt.get("state") in ("not_started", "ended"):
                continue
            found = self._find(attempt_id)
            if found is None and not settle_missing:
                continue
            if found is None:
                self._write({"attempt_id": attempt_id, "state": "not_started", "at": self._at()})
                self.say(f"attempt {attempt_id} (row {attempt['order']}) never started a match")
            else:
                self._write({"attempt_id": attempt_id, "match_id": found["id"], "state": "started"})
                self.say(f"attempt {attempt_id} started match {found['id']}: adopted")

    # --- running ------------------------------------------------------------------------------

    def _at(self) -> str:
        return self.now().isoformat()

    def run(self) -> list[dict[str, Any]]:
        """Play the open rows in order, one at a time. RunStopped on any hold."""
        self.out.mkdir(parents=True, exist_ok=True)
        held = [a for a in self.attempts().values() if a.get("hold")]
        if held and not self.resume_after_hold:
            raise RunStopped(
                f"held after row {held[-1]['order']}: {held[-1]['hold']} (go on only with "
                "--resume-after-hold, after a person decided)"
            )
        self.reconcile()
        attempts = self.attempts()
        for attempt in attempts.values():  # a match that ran when the client stopped
            if attempt.get("match_id") and attempt.get("state") != "ended":
                self._finish(attempt["attempt_id"], attempt)
        attempts = self.attempts()
        tried = {a["order"] for a in attempts.values() if a.get("state") != "not_started"}
        for row in self.matches:
            if int(row["order"]) in tried:
                continue  # played or tried once: never again (no retries)
            checks = self.gates(row)
            attempt_id = uuid.uuid4().hex[:12]
            body = self.body(row, attempt_id)
            self._write(
                {
                    "attempt_id": attempt_id,
                    "order": int(row["order"]),
                    "guest": row["guest"],
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
                self.reconcile(settle_missing=False)
                if not self.attempts()[attempt_id].get("match_id"):
                    raise RunStopped(
                        f"row {row['order']}: no answer to its POST and no match found yet; "
                        "run again later: the next run decides whether it started"
                    ) from error
                record = {"id": self.attempts()[attempt_id]["match_id"]}
                status = 201
            if status != 201:
                self._write({"attempt_id": attempt_id, "state": "not_started", "refused": status})
                raise RunStopped(f"the arena refused row {row['order']} ({status}): {record}")
            self._write({"attempt_id": attempt_id, "match_id": record["id"], "state": "started"})
            self.say(f"row {row['order']} started as match {record['id']} ({row['guest']})")
            self._finish(attempt_id, self.attempts()[attempt_id])
        return [a for a in self.attempts().values() if a.get("state") == "ended"]

    def _finish(self, attempt_id: str, attempt: dict[str, Any]) -> None:
        match_id = attempt["match_id"]
        record = {"status": "running"}
        while record["status"] not in ENDED:
            record = self._get(f"/matches/{match_id}")
            if record["status"] not in ENDED:
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
        seats = {f"p{i}": row[f"p{i}"] for i in range(1, 9)}
        reports = seat_reports(events, seats)
        guest = reports[row["guest_seat"]]
        share = guest.fallbacks / guest.turns if guest.turns else 1.0
        dealt = next(
            (
                e["data"].get("role")
                for e in events
                if e.get("type") == "role_assigned"
                and (e.get("data") or {}).get("player") == row["guest_seat"]
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
                "guest_fallback_share": round(share, 4),
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
            holds.append(f"guest fallback share {share:.0%}")
        if dealt != row["expected_role"]:
            holds.append(f"guest dealt {dealt}, planned {row['expected_role']}")
        if holds:
            reason = "; ".join(holds)
            self._write({"attempt_id": attempt_id, "hold": reason})
            raise RunStopped(f"row {row['order']}: {reason}: hold and report")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m arena.research.guest_runner",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("plan", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--api", default="http://127.0.0.1:8100")
    parser.add_argument("--confirm-spend", action="store_true", required=True)
    parser.add_argument("--poll", type=float, default=10)
    parser.add_argument(
        "--resume-after-hold",
        action="store_true",
        help="go on after a hold, once a person has decided to (the held row is not replayed)",
    )
    args = parser.parse_args(argv)
    sys.stdout.reconfigure(errors="backslashreplace", line_buffering=True)
    try:
        runner = GuestRunner(
            args.plan,
            args.out,
            http_request(args.api),
            poll=args.poll,
            resume_after_hold=args.resume_after_hold,
        )
        ended = runner.run()
    except PlanRefused as refused:
        print(f"Refused: {refused}", file=sys.stderr)
        return 2
    except RunStopped as stop:
        print(f"Held: {stop}")
        return 3
    print(f"Done: {len(ended)} matches, stage {runner.spent() / MICRO:.6f} EUR")
    return 0


if __name__ == "__main__":
    sys.exit(main())
