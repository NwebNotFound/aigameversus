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

`--bots` plays the same schedule with random bots, for free: a dry run of the
runner against a live server.
"""

import argparse
import json
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
        self.settings = {**experiment.settings, **(settings or {})}
        self.game = experiment.game
        self.out = out
        self.request = request
        self.turn_delay = turn_delay
        self.pause = pause
        self.poll = poll
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

    def check_budget(self) -> None:
        """Raise RunStopped if the next match may not start for money reasons."""
        lines = (
            self.log_path.read_text(encoding="utf-8").splitlines() if self.log_path.exists() else []
        )
        spent = self.spent()
        if spent >= self.budget * STOP_SHARE:
            raise RunStopped(
                f"cost {spent / MICRO:.4f} EUR has reached 90 % of the budget "
                f"{self.budget / MICRO:.2f} EUR"
            )
        if lines:
            mean = spent / len(lines)
            if spent + 2 * mean > self.budget:
                raise RunStopped(
                    f"cost {spent / MICRO:.4f} EUR plus twice the mean match "
                    f"({mean / MICRO:.4f} EUR) would pass the budget {self.budget / MICRO:.2f} EUR"
                )

    def run(self) -> list[MatchReport]:
        """Play every open match of the run; return all reports. Raises RunStopped."""
        self.out.mkdir(parents=True, exist_ok=True)
        if not self.pilot and isinstance(self.stage, League) and self.stage.pilot_tables:
            pilot = [r for r in self.done() if r.pilot]
            if problems := pilot_problems(pilot):
                raise RunStopped("pilot rule broken: " + "; ".join(problems))
        finished = {r.order for r in self.done() if r.status == "finished"}
        attempts = Counter(r.order for r in self._all_lines())
        for match in self.matches:
            if match.order in finished:
                continue
            while True:
                self.check_budget()
                attempt = attempts[match.order] + 1
                report = self.play(match, attempt)
                attempts[match.order] = attempt
                if report.status == "finished" or attempt >= 2:
                    break
                self.say(f"match {match.order} ended {report.status}: playing it once more")
            if self.pause:
                self.sleep(self.pause)
        reports = self.done()
        if self.pilot and (problems := pilot_problems(reports)):
            raise RunStopped("pilot rule broken: " + "; ".join(problems))
        return reports

    def _all_lines(self) -> list[MatchReport]:
        if not self.log_path.exists():
            return []
        lines = []
        for line in self.log_path.read_text(encoding="utf-8").splitlines():
            data = json.loads(line)
            data["seats"] = {p: SeatReport(**s) for p, s in data["seats"].items()}
            lines.append(MatchReport(**data))
        return lines

    def play(self, match: ScheduledMatch, attempt: int = 1) -> MatchReport:
        """Start one match, wait until it has ended, write its log and report."""
        models = [seat.split("@")[0] for seat in match.seats]
        body: dict[str, Any] = {
            "game": self.game,
            "seed": match.seed,
            "settings": self.settings,
            "turn_delay": self.turn_delay,
        }
        if self.bots:
            body["players"] = len(models)
        else:
            body["models"] = models
            body["confirm_spend"] = True
        status, record = self.request("POST", "/matches", body)
        if status != 201:
            raise RunStopped(f"the arena refused match {match.order} ({status}): {record}")
        match_id = record["id"]
        total = len(self.matches)
        self.say(
            f"match {match.order} ({self.matches.index(match) + 1} of {total}) started: "
            f"{self.web}/matches/{match_id}  seats {' '.join(models)}"
        )
        while record["status"] not in ENDED:
            self.sleep(self.poll)
            status, record = self.request("GET", f"/matches/{match_id}", None)
            if status != 200:
                raise RunStopped(f"lost match {match_id} ({status}): {record}")
        _, events = self.request("GET", f"/matches/{match_id}/events", None)
        status, cost = self.request("GET", f"/matches/{match_id}/cost", None)
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
            f"run so far {self.spent() / MICRO:.4f} of {self.budget / MICRO:.2f} EUR"
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
    parser.add_argument("--pause", type=float, default=0, help="seconds between matches")
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
