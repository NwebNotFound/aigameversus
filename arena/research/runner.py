"""Play the matches of an experiment stage through the arena API, one at a time.

    uv run python -m arena.research.runner experiments/E1_liars_deck.yaml --stage A --pilot \\
        --out runs/E1-A --confirm-spend

Each match of the stage's schedule is started with `POST /matches` (model
seats, `confirm_spend`), its live address is printed, and the runner waits
until it has ended before the next one starts. What happened is appended to
`<out>/runs.jsonl`, one line per match, and the log of each match is saved as
`<out>/<order>.json`; a second start continues after the last finished line.

The runner stops, before it starts a match, when
- the cost of the run has reached 90 % of its budget,
- the cost so far plus twice the mean cost of a match would pass the budget,
- after the pilot: a model played more than 10 % of its turns by fallback, or
  lost its agent in 2 or more of its matches (the plan's pilot rule).
The budget is the stage's (`budget_eur`), or the pilot's (`pilot_budget_eur`)
with `--pilot`. These stops come on top of the arena's caps per match and per
month, which the server enforces on every call.

Drain and resume (e.g. for a rebuild of the arena): create `<out>/DRAIN`; the
runner starts nothing more, waits for the running matches and stops. Delete the
file and start the runner again; it continues from runs.jsonl and started.jsonl.

`--bots` plays the same schedule with random bots, for free: a dry run of the
runner against a live server.
"""

import argparse
import json
import random
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any

from arena.research.experiment import (
    Experiment,
    League,
    PlanError,
    ScheduledMatch,
    load_experiment,
    schedule,
)

MICRO = 1_000_000
STOP_SHARE = Decimal("0.9")  # of the budget
FALLBACK_LIMIT = 0.10  # share of a model's turns
FAILED_AGENT_LIMIT = 2  # matches of one model in which its agent gave up
ENDED = {"finished", "failed", "interrupted", "aborted"}
MAX_PARALLEL = 8  # the arena plays at most 10 matches at a time

# One call of the arena API: method, path, JSON body or None -> status, JSON answer.
Request = Callable[[str, str, Any], tuple[int, Any]]


class RunStopped(Exception):
    """The run stopped before a match; the message says why."""


@dataclass
class SeatReport:
    """What one seat of one match did, read from its log."""

    model: str
    turns: int = 0  # accepted moves plus moves played by the fallback
    fallbacks: int = 0
    rejected: int = 0
    agent_failed: bool = False


@dataclass
class MatchReport:
    order: int
    stage: str
    table: str
    seating: int
    replicate: int
    seed: int
    pilot: bool
    match_id: str
    status: str
    cost_micro_eur: int
    placements: list[dict[str, Any]]
    seats: dict[str, SeatReport] = field(default_factory=dict)
    prompt_version: str | None = None
    attempt: int = 1


def http_request(base: str, timeout: float = 30) -> Request:
    """Calls to the arena API at `base`, standard library only."""

    def call(method: str, path: str, body: Any) -> tuple[int, Any]:
        data = None if body is None else json.dumps(body).encode()
        request = urllib.request.Request(
            base.rstrip("/") + path,
            data=data,
            method=method,
            headers={"content-type": "application/json"} if data else {},
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as answer:
                return answer.status, json.loads(answer.read() or b"null")
        except urllib.error.HTTPError as error:
            try:
                detail = json.loads(error.read() or b"null")
            except ValueError:
                detail = None
            return error.code, detail

    return call


def seat_reports(events: Iterable[Mapping[str, Any]], seats: Mapping[str, str]) -> dict:
    """Turns, fallbacks, rejected answers and failed agents per seat, from a match log."""
    reports = {player: SeatReport(model=model) for player, model in seats.items()}
    for event in events:
        data = event.get("data") or {}
        player = data.get("player")
        if player not in reports:
            continue
        match event.get("type"):
            case "action_accepted":
                reports[player].turns += 1
            case "action_fallback":
                reports[player].turns += 1
                reports[player].fallbacks += 1
            case "action_rejected":
                reports[player].rejected += 1
            case "agent_failed":
                reports[player].agent_failed = True
    return reports


def pilot_problems(reports: Sequence[MatchReport]) -> list[str]:
    """The pilot rule of the plan: one line per model that breaks it."""
    turns: Counter[str] = Counter()
    fallbacks: Counter[str] = Counter()
    failed: Counter[str] = Counter()
    for report in reports:
        for seat in report.seats.values():
            turns[seat.model] += seat.turns
            fallbacks[seat.model] += seat.fallbacks
            failed[seat.model] += seat.agent_failed
    problems = []
    for model in sorted(turns):
        share = fallbacks[model] / turns[model] if turns[model] else 1.0
        if share > FALLBACK_LIMIT:
            problems.append(f"{model}: {share:.0%} of its turns played by the fallback")
        if failed[model] >= FAILED_AGENT_LIMIT:
            problems.append(f"{model}: agent failed in {failed[model]} matches")
    return problems


def model_summary(reports: Sequence[MatchReport]) -> list[dict[str, Any]]:
    """Per model: matches, turns, fallback share, rejected answers, failed agents, cost."""
    rows: dict[str, dict[str, Any]] = {}
    for report in reports:
        for seat in report.seats.values():
            row = rows.setdefault(
                seat.model,
                {
                    "model": seat.model,
                    "matches": 0,
                    "turns": 0,
                    "fallbacks": 0,
                    "rejected": 0,
                    "agent_failed": 0,
                },
            )
            row["matches"] += 1
            row["turns"] += seat.turns
            row["fallbacks"] += seat.fallbacks
            row["rejected"] += seat.rejected
            row["agent_failed"] += seat.agent_failed
    for row in rows.values():
        row["fallback_share"] = round(row["fallbacks"] / row["turns"], 4) if row["turns"] else None
    return [rows[model] for model in sorted(rows)]


class Runner:
    def __init__(
        self,
        experiment: Experiment,
        stage_id: str,
        out: Path,
        request: Request,
        *,
        pilot: bool = False,
        bots: bool = False,
        settings: Mapping[str, Any] | None = None,
        turn_delay: float = 0,
        pause: float = 0,
        poll: float = 5,
        parallel: int = 1,
        per_model: int = 3,
        match_bound_eur: float = 0.08,
        batch: tuple[str, str] | None = None,
        web: str = "http://127.0.0.1:3100",
        sleep: Callable[[float], None] = time.sleep,
        say: Callable[[str], None] = print,
    ):
        stages = {stage.id: stage for stage in experiment.stages}
        if stage_id not in stages:
            raise PlanError(f"no stage {stage_id!r}; the plan has {', '.join(stages)}")
        stage = stages[stage_id]
        if pilot and not (isinstance(stage, League) and stage.pilot_tables):
            raise PlanError(f"stage {stage_id} has no pilot")
        if not bots and not any(
            stage_id in entry.get("stages", ()) for entry in experiment.approvals
        ):
            raise PlanError(f"stage {stage_id} has no entry under approvals: it may not spend")
        self.stage = stage
        self.pilot = pilot
        self.bots = bots
        budget = stage.pilot_budget_eur if pilot else stage.budget_eur
        self.budget = int(budget * MICRO)
        self.matches = [
            match
            for match in schedule(experiment)
            if match.stage == stage_id and (match.pilot if pilot else True)
        ]
        self.settings = {**experiment.settings, **stage.settings, **(settings or {})}
        self.game = experiment.game
        self.out = out
        self.request = request
        self.turn_delay = turn_delay
        self.pause = pause
        self.poll = poll
        if not 1 <= parallel <= MAX_PARALLEL:
            raise PlanError(f"parallel must be 1 to {MAX_PARALLEL}")
        self.parallel = parallel
        self.per_model = per_model
        self.match_bound = int(match_bound_eur * MICRO)
        self.batch = batch  # (id, label): sent with every start, so the arena can group the run
        self.web = web.rstrip("/")
        self.sleep = sleep
        self.say = say

    @property
    def log_path(self) -> Path:
        return self.out / "runs.jsonl"

    def done(self) -> list[MatchReport]:
        """The matches of this run that ended, as written to the log (last attempt each)."""
        last = {report.order: report for report in self._all_lines()}
        return [last[order] for order in sorted(last)]

    def spent(self) -> int:
        """What this run has cost, all attempts included, in millionths of a euro."""
        if not self.log_path.exists():
            return 0
        return sum(
            json.loads(line)["cost_micro_eur"]
            for line in self.log_path.read_text(encoding="utf-8").splitlines()
        )

    def check_budget(self, running: int = 0, running_cost: Sequence[int] = ()) -> None:
        """Raise RunStopped if no further match may start for money reasons.

        `running` matches have started and not ended; each counts with what it
        has cost so far (`running_cost`) or `match_bound`, whichever is higher.
        The run stops starting matches when what it has spent, plus that for
        every running match, plus `match_bound` for the next one would pass 90 %
        of the budget, or when the mean match for each of them and two more
        would pass the budget.
        """
        spent = self.spent()
        lines = len(self._all_lines())
        limit = self.budget * STOP_SHARE
        if spent >= limit:
            raise RunStopped(
                f"cost {spent / MICRO:.4f} EUR has reached 90 % of the budget "
                f"{self.budget / MICRO:.2f} EUR"
            )
        held = sum(max(cost, self.match_bound) for cost in running_cost)
        held += max(0, running - len(running_cost)) * self.match_bound
        if running and spent + held + self.match_bound > limit:
            raise RunStopped(
                f"cost {spent / MICRO:.4f} EUR plus {running + 1} matches at up to "
                f"{self.match_bound / MICRO:.2f} EUR would pass 90 % of the budget"
            )
        if lines:
            mean = spent / lines
            if spent + (running + 2) * mean > self.budget:
                raise RunStopped(
                    f"cost {spent / MICRO:.4f} EUR plus twice the mean match "
                    f"({mean / MICRO:.4f} EUR) would pass the budget {self.budget / MICRO:.2f} EUR"
                )

    def check_month(self, running: int) -> None:
        """Stop starting when the month has less left than the running matches may cost."""
        status, month = self.request("GET", "/ledger/month", None)
        if status != 200 or not isinstance(month, dict):
            return  # a server without the endpoint: its own cap still holds on every call
        if month["remaining_micro_eur"] < (running + 1) * self.match_bound:
            raise RunStopped(
                f"the month has {month['remaining_micro_eur'] / MICRO:.2f} EUR left: "
                "not enough for another match"
            )

    def run(self) -> list[MatchReport]:
        """Play every open match of the run, up to `parallel` at a time. Raises RunStopped.

        Matches start in schedule order, skipping one whose models already play
        `per_model` matches. A match that was started but not logged (the
        runner stopped while it ran) is waited for, not started again.
        """
        self.out.mkdir(parents=True, exist_ok=True)
        if not self.pilot and isinstance(self.stage, League) and self.stage.pilot_tables:
            pilot = [r for r in self.done() if r.pilot]
            if problems := pilot_problems(pilot):
                raise RunStopped("pilot rule broken: " + "; ".join(problems))
        finished = {r.order for r in self.done() if r.status == "finished"}
        attempts = Counter(r.order for r in self._all_lines())
        by_order = {match.order: match for match in self.matches}
        running: dict[str, tuple[ScheduledMatch, int]] = {}
        logged = {r.match_id for r in self._all_lines()}
        for order, match_id in self._started().items():
            if match_id not in logged and order not in finished and order in by_order:
                running[match_id] = (by_order[order], attempts[order] + 1)
                self.say(f"match {order} was running when the runner stopped: waiting for it")
        busy = {match.order for match, _ in running.values()}
        pending = [m for m in self.matches if m.order not in finished and m.order not in busy]
        stop: RunStopped | None = None
        while running or (pending and stop is None):
            if stop is None and pending and self.drain_path.exists():
                stop = RunStopped(f"drained: {self.drain_path} exists; no new match started")
                self.say(f"draining: waiting for {len(running)} running matches")
            while stop is None and pending and len(running) < self.parallel:
                load = Counter(
                    seat.split("@")[0] for match, _ in running.values() for seat in match.seats
                )
                match = next(
                    (
                        m
                        for m in pending
                        if all(load[seat.split("@")[0]] < self.per_model for seat in m.seats)
                    ),
                    None,
                )
                if match is None:
                    break
                try:
                    self.check_budget(len(running), self.running_costs(running))
                    if not self.bots:
                        self.check_month(len(running))
                except RunStopped as stopped:
                    stop = stopped
                    self.say(f"no new match: {stopped}; waiting for {len(running)} running")
                    break
                match_id = self.start(match)
                if match_id is None:  # the arena is full: try again after the next poll
                    break
                pending.remove(match)
                running[match_id] = (match, attempts[match.order] + 1)
                if self.pause:
                    self.sleep(self.pause)
            if not running:
                break
            self.sleep(self.poll)
            for match_id, (match, attempt) in list(running.items()):
                status, record = self.request("GET", f"/matches/{match_id}", None)
                if status != 200:
                    raise RunStopped(f"lost match {match_id} ({status}): {record}")
                if record["status"] not in ENDED:
                    continue
                del running[match_id]
                report = self.finish(match, match_id, record, attempt)
                attempts[match.order] = attempt
                if report.status != "finished" and attempt < 2:
                    self.say(f"match {match.order} ended {report.status}: playing it once more")
                    pending.insert(0, match)
        if stop is not None:
            raise stop
        reports = self.done()
        if self.pilot and (problems := pilot_problems(reports)):
            raise RunStopped("pilot rule broken: " + "; ".join(problems))
        return reports

    def running_costs(self, running: Mapping[str, Any]) -> list[int]:
        """What each running match has cost so far; the bound for one whose cost is unknown."""
        costs = []
        for match_id in running:
            status, cost = self.request("GET", f"/matches/{match_id}/cost", None)
            ok = status == 200 and isinstance(cost, dict)
            costs.append(cost["total_micro_eur"] if ok else self.match_bound)
        return costs

    @property
    def drain_path(self) -> Path:
        """While this file exists the run starts no match; running ones play to the end."""
        return self.out / "DRAIN"

    @property
    def started_path(self) -> Path:
        return self.out / "started.jsonl"

    def _started(self) -> dict[int, str]:
        """Order -> id of the last match started for it."""
        if not self.started_path.exists():
            return {}
        started = {}
        for line in self.started_path.read_text(encoding="utf-8").splitlines():
            data = json.loads(line)
            started[data["order"]] = data["match_id"]
        return started

    def _all_lines(self) -> list[MatchReport]:
        if not self.log_path.exists():
            return []
        lines = []
        for line in self.log_path.read_text(encoding="utf-8").splitlines():
            data = json.loads(line)
            data["seats"] = {p: SeatReport(**s) for p, s in data["seats"].items()}
            lines.append(MatchReport(**data))
        return lines

    def start(self, match: ScheduledMatch) -> str | None:
        """Start one match and note it in started.jsonl.

        None while the arena is full (429) or its ledger is down (503) after five
        tries with growing, jittered pauses: the caller tries again later.
        """
        models = [seat.split("@")[0] for seat in match.seats]
        body: dict[str, Any] = {
            "game": self.game,
            "seed": match.seed,
            "settings": self.settings,
            "turn_delay": self.turn_delay,
            "memory": False,  # experiments are played without memory: nothing read, nothing written
        }
        if self.batch is not None:
            batch_id, label = self.batch
            index = self.matches.index(match) + 1
            body["batch"] = {
                "id": batch_id,
                "label": label,
                "index": index,
                "of": len(self.matches),
            }
        if self.bots:
            body["players"] = len(models)
        else:
            body["models"] = models
            body["confirm_spend"] = True
        for tries in range(5):
            status, record = self.request("POST", "/matches", body)
            if status not in (429, 503):  # full, or the ledger is down: wait and try again
                break
            self.sleep(self.poll * (2**tries) * (1 + random.random()))  # backoff with jitter
        else:
            return None
        if status != 201:
            raise RunStopped(f"the arena refused match {match.order} ({status}): {record}")
        match_id = record["id"]
        with self.started_path.open("a", encoding="utf-8", newline="\n") as log:
            log.write(json.dumps({"order": match.order, "match_id": match_id}) + "\n")
        self.say(
            f"match {match.order} ({self.matches.index(match) + 1} of {len(self.matches)}) "
            f"started: {self.web}/matches/{match_id}  seats {' '.join(models)}"
        )
        return match_id

    def play(self, match: ScheduledMatch, attempt: int = 1) -> MatchReport:
        """Start one match, wait until it has ended, write its log and report."""
        match_id = self.start(match)
        if match_id is None:
            raise RunStopped(f"the arena stayed full: match {match.order} did not start")
        record: dict[str, Any] = {"status": "running"}
        while record["status"] not in ENDED:
            self.sleep(self.poll)
            status, record = self.request("GET", f"/matches/{match_id}", None)
            if status != 200:
                raise RunStopped(f"lost match {match_id} ({status}): {record}")
        return self.finish(match, match_id, record, attempt)

    def finish(
        self, match: ScheduledMatch, match_id: str, record: dict[str, Any], attempt: int
    ) -> MatchReport:
        """Read the log and cost of an ended match, save them and append its line."""
        models = [seat.split("@")[0] for seat in match.seats]
        _, events = self.request("GET", f"/matches/{match_id}/events", None)
        for tries in range(5):
            status, cost = self.request("GET", f"/matches/{match_id}/cost", None)
            if status != 503:
                break
            self.sleep(self.poll * (2**tries))
        if status != 200:
            raise RunStopped(f"no cost for match {match_id} ({status}): stop and check the ledger")
        seats = {f"p{n}": model for n, model in enumerate(models, start=1)}
        report = MatchReport(
            order=match.order,
            stage=match.stage,
            table=match.table,
            seating=match.seating,
            replicate=match.replicate,
            seed=match.seed,
            pilot=match.pilot,
            match_id=match_id,
            status=record["status"],
            cost_micro_eur=cost["total_micro_eur"],
            placements=record.get("placements") or [],
            seats=seat_reports(events or [], seats),
            prompt_version=record.get("prompt_version"),
            attempt=attempt,
        )
        saved = {"record": record, "cost": cost, "events": events}
        name = f"{match.order:03d}" + ("" if attempt == 1 else f"-attempt{attempt}")
        (self.out / f"{name}.json").write_text(
            json.dumps(saved, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n"
        )
        line = {**report.__dict__, "seats": {p: s.__dict__ for p, s in report.seats.items()}}
        with self.log_path.open("a", encoding="utf-8", newline="\n") as log:
            log.write(json.dumps(line) + "\n")
        self.say(
            f"match {match.order} {report.status}, {report.cost_micro_eur / MICRO:.4f} EUR; "
            f"run so far {self.spent() / MICRO:.4f} of {self.budget / MICRO:.2f} EUR, "
            f"{len(self.done())} of {len(self.matches)} done"
        )
        return report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m arena.research.runner",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("plan", type=Path)
    parser.add_argument("--stage", required=True)
    parser.add_argument(
        "--out", type=Path, required=True, help="folder for the run log and match logs"
    )
    parser.add_argument("--pilot", action="store_true", help="play only the stage's pilot matches")
    seats = parser.add_mutually_exclusive_group(required=True)
    seats.add_argument(
        "--confirm-spend", action="store_true", help="model seats: this spends money"
    )
    seats.add_argument("--bots", action="store_true", help="random bots in every seat: free")
    parser.add_argument("--setting", action="append", default=[], metavar="NAME=VALUE")
    parser.add_argument("--api", default="http://127.0.0.1:8100")
    parser.add_argument("--web", default="http://127.0.0.1:3100")
    parser.add_argument("--turn-delay", type=float, default=0)
    parser.add_argument("--pause", type=float, default=0, help="seconds between match starts")
    parser.add_argument("--parallel", type=int, default=1, help="matches at a time (1 to 8)")
    parser.add_argument(
        "--per-model", type=int, default=3, help="most matches one model plays at a time"
    )
    parser.add_argument(
        "--match-bound", type=float, default=0.08, help="EUR a running match may still cost"
    )
    parser.add_argument(
        "--batch-id", help="send a batch field with every start (needs --batch-label)"
    )
    parser.add_argument("--batch-label", help="the batch's name as people read it")
    args = parser.parse_args(argv)
    sys.stdout.reconfigure(errors="backslashreplace", line_buffering=True)
    settings = {}
    for pair in args.setting:
        name, _, value = pair.partition("=")
        try:
            settings[name] = json.loads(value)
        except ValueError:
            settings[name] = value
    try:
        runner = Runner(
            load_experiment(args.plan),
            args.stage,
            args.out,
            http_request(args.api),
            pilot=args.pilot,
            bots=args.bots,
            settings=settings,
            turn_delay=args.turn_delay,
            pause=args.pause,
            parallel=args.parallel,
            per_model=args.per_model,
            match_bound_eur=args.match_bound,
            batch=(args.batch_id, args.batch_label) if args.batch_id else None,
            web=args.web,
        )
        reports = runner.run()
    except PlanError as error:
        print(error, file=sys.stderr)
        return 2
    except RunStopped as stop:
        print(f"Stopped: {stop}")
        print(json.dumps(model_summary(runner.done()), indent=1))
        return 3
    print(f"Done: {len(reports)} matches, {runner.spent() / MICRO:.4f} EUR")
    print(json.dumps(model_summary(reports), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
