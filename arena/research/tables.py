"""Serial, explicit-table API client. Dry-run by default; no provider/key access.

Only tables in the hashed CSV may start. Server batch history is authoritative
for cumulative spend. An ambiguous POST is never retried automatically.
"""

import argparse
import csv
import hashlib
import json
import os
import time
from collections import Counter
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from arena.research.runner import RunStopped, http_request, seat_reports


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def save(path, value):
    """Write/flush intent before dispatch; replace atomically on the same volume."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    tmp.replace(path)


@contextmanager
def lock(root):
    root.mkdir(parents=True, exist_ok=True)
    path = root / "CLIENT.lock"
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as error:
        raise RunStopped(
            "Client lock exists; verify the prior process ended before manual removal"
        ) from error
    try:
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        yield
    finally:
        path.unlink()


def load_job(path):
    job = read_json(path)
    allowed = {
        "stage",
        "batch",
        "approval",
        "csv",
        "csv_sha256",
        "budget_micro_eur",
        "match_micro_eur",
        "reservation_micro_eur",
        "smoke",
        "requires_c1_smoke",
        "guest_price_ceilings",
        "expected_history_limit_events",
        "execution_plan_approved",
        "execution_approval_evidence",
    }
    if set(job) - {"reviewed_c1_outcome"} != allowed or job["stage"] not in {"C1", "W2"}:
        raise RunStopped("Unknown or missing job fields")
    expected = (
        (1_000_000, 200_000, 200_000) if job["stage"] == "C1" else (3_500_000, 400_000, 400_000)
    )
    if (
        tuple(job[k] for k in ("budget_micro_eur", "match_micro_eur", "reservation_micro_eur"))
        != expected
    ):
        raise RunStopped("Job budget differs from approved stage")
    if not job["approval"] or job["batch"] != job["stage"]:
        raise RunStopped("Missing approval or noncanonical batch id")
    if job["smoke"] != (job["stage"] == "C1") or job["requires_c1_smoke"] != (job["stage"] == "W2"):
        raise RunStopped("Smoke gate changed")
    if job["expected_history_limit_events"] != (120 if job["stage"] == "C1" else 40):
        raise RunStopped("Unexpected research history-window metadata")
    csv_path = path.parent / job["csv"]
    if hashlib.sha256(csv_path.read_bytes()).hexdigest() != job["csv_sha256"]:
        raise RunStopped("CSV hash changed")
    rows = []
    with csv_path.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        if len(reader.fieldnames or []) != 7 or set(reader.fieldnames or []) != {
            "order",
            "game",
            "models",
            "seed",
            "settings",
            "memory",
            "estimate_micro_eur",
        }:
            raise RunStopped("CSV columns differ from explicit-table schema")
        for index, raw in enumerate(reader, 1):
            row = {
                "order": int(raw["order"]),
                "game": raw["game"],
                "models": json.loads(raw["models"]),
                "seed": int(raw["seed"]),
                "settings": json.loads(raw["settings"]),
                "memory": json.loads(raw["memory"]),
                "estimate_micro_eur": int(raw["estimate_micro_eur"]),
            }
            if row["order"] != index or row["memory"] is not False or not 0 <= row["seed"] < 2**63:
                raise RunStopped("Nonsequential table or memory enabled")
            expected_game, n = ("civ", 4) if job["stage"] == "C1" else ("werewolf", 8)
            if (
                row["game"] != expected_game
                or not isinstance(row["models"], list)
                or len(row["models"]) != n
                or not all(isinstance(m, str) and m for m in row["models"])
            ):
                raise RunStopped("Unexpected game/models")
            settings = row["settings"]
            required = (
                {
                    "rounds": 20,
                    "prompt_version": "civ-p1",
                    "strategy_text": "off",
                    "private_plan": "off",
                }
                if job["smoke"]
                else {"template": "classic", "language": "en", "prompt_version": "werewolf-p2"}
            )
            required.update(
                answer_repair="off", match_budget_eur=job["match_micro_eur"] / 1_000_000
            )
            if settings != required or not 0 < row["estimate_micro_eur"] < 400_000:
                raise RunStopped("Unapproved settings or estimate")
            rows.append(row)
    if len(rows) != (4 if job["smoke"] else 8):
        raise RunStopped("Wrong table count")
    return job, rows


def start_allowed(spent, estimate, job, month):
    """Integer micro-EUR; both independent reservations must fit."""
    if month >= 20_000_000:
        raise RunStopped("Monthly notify/hold at EUR20")
    if not 0 < estimate < 400_000:
        raise RunStopped("Estimate is not strictly below EUR0.40")
    if spent + 3 * estimate > job["budget_micro_eur"] * 9 // 10:
        raise RunStopped("Three-times estimate exceeds 90% stage start bound")
    if spent + job["reservation_micro_eur"] > job["budget_micro_eur"]:
        raise RunStopped("Full reservation exceeds cumulative stage allowance")
    if month + job["match_micro_eur"] > 25_000_000:
        raise RunStopped("Monthly hard reservation does not fit")


class Tables:
    def __init__(
        self,
        job_path,
        root,
        request,
        *,
        sleep=time.sleep,
        say=print,
        now=time.time,
        max_wait_seconds=3600,
    ):
        self.job, self.rows = load_job(job_path)
        self.root = root
        self.out = root / self.job["stage"]
        self.out.mkdir(parents=True, exist_ok=True)
        self.request, self.sleep, self.say = request, sleep, say
        if not 0 < max_wait_seconds <= 3600:
            raise RunStopped("Active wait must be bounded at one hour or less")
        self.now, self.max_wait_seconds = now, max_wait_seconds
        self.path = self.out / "run.json"
        self.frozen = digest({"job": self.job, "rows": self.rows})
        self.state = (
            read_json(self.path)
            if self.path.exists()
            else {"frozen": self.frozen, "intents": {}, "reports": {}}
        )
        if self.state["frozen"] != self.frozen:
            raise RunStopped("Existing run has different frozen inputs")

    def get(self, path):
        status, data = self.request("GET", path, None)
        if status != 200:
            raise RunStopped(f"GET {path} refused ({status})")
        return data

    def persist(self):
        save(self.path, self.state)

    def body(self, row):
        # Whitelist, never forward plan/role-map/approval metadata to players.
        return {k: row[k] for k in ("game", "models", "seed", "settings", "memory")}

    def verify_record(self, record, row):
        if (
            record["game"] != row["game"]
            or record["seed"] != row["seed"]
            or record["memory"] is not False
        ):
            raise RunStopped("Server batch table does not match frozen input")
        if any(record["settings"].get(k) != v for k, v in row["settings"].items()):
            raise RunStopped("Server settings differ from frozen table")
        models = [record["seats"][f"p{i}"]["model_id"] for i in range(1, len(row["models"]) + 1)]
        if models != row["models"]:
            raise RunStopped("Server roster differs from frozen table")

    def history(self):
        records = self.get(f"/matches?batch={self.job['batch']}")
        if len(records) >= 1000:
            raise RunStopped("Batch history may be truncated")
        by_order = {}
        spent = 0
        for record in records:
            order = record["batch"].get("index")
            if type(order) is not int or not 1 <= order <= len(self.rows) or order in by_order:
                raise RunStopped("Unknown/duplicate server batch index: reconcile manually")
            self.verify_record(record, self.rows[order - 1])
            by_order[order] = record
            cost = self.get(f"/matches/{record['id']}/cost")["total_micro_eur"]
            if type(cost) is not int or cost < 0:
                raise RunStopped("Invalid ledger cost")
            spent += cost
        if set(by_order) != set(range(1, len(by_order) + 1)):
            raise RunStopped("Server history has a gap in the fixed order")
        if spent > self.job["budget_micro_eur"]:
            raise RunStopped("Cumulative stage cost exceeded")
        # A fresh output directory cannot erase server history or start duplicates.
        for order, intent in self.state["intents"].items():
            record = by_order.get(int(order))
            if record is None:
                raise RunStopped("Unresolved POST intent; never resend automatically")
            if intent.get("match_id") not in (None, record["id"]):
                raise RunStopped("Intent/server match id differs")
        return by_order, spent

    def observe(self, row, record):
        events = self.get(f"/matches/{record['id']}/events")
        cost = self.get(f"/matches/{record['id']}/cost")["total_micro_eur"]
        seats = seat_reports(events, {f"p{i}": m for i, m in enumerate(row["models"], 1)})
        turns, fallbacks = Counter(), Counter()
        reasons = []
        for seat in seats.values():
            turns[seat.model] += seat.turns
            fallbacks[seat.model] += seat.fallbacks
            if seat.agent_failed:
                reasons.append("failed agent")
        if any(fallbacks[m] * 10 > n for m, n in turns.items()):
            reasons.append("model fallback above 10%")
        if record["status"] not in {"running", "finished"}:
            reasons.append(f"match {record['status']}")
        intent = self.state["intents"].get(str(row["order"]), {})
        if record["status"] == "running":
            deadline = intent.get("wait_deadline_epoch")
            if deadline is None and record.get("started_at"):
                deadline = (
                    datetime.fromisoformat(record["started_at"].replace("Z", "+00:00")).timestamp()
                    + self.max_wait_seconds
                )
            if deadline is None or self.now() > deadline:
                reasons.append("active wait deadline exceeded or unavailable")
        quote = intent.get("estimate_micro_eur", row["estimate_micro_eur"])
        jump_limit = (
            160_000
            if self.job["smoke"] and row["order"] == 1
            else min(self.job["match_micro_eur"], 2 * quote)
        )
        if cost > jump_limit:
            reasons.append("actual cost jump/smoke limit")
        if any(e["type"] == "match_paused" for e in events):
            reasons.append("match paused: no automatic resume")
        starts = [e for e in events if e["type"] == "match_started"]
        if (
            not starts
            or starts[0]["data"].get("settings", {}).get("match_budget_eur")
            != row["settings"]["match_budget_eur"]
        ):
            reasons.append("missing/mismatched recorded spend setting")
        if record["status"] == "finished" and not sum(turns.values()):
            reasons.append("finished match has no observed decisions")
        if self.job["stage"] == "W2":
            guest = next(f"p{i}" for i, m in enumerate(row["models"], 1) if "/" in m)
            roles = {
                e["data"]["player"]: e["data"]["role"]
                for e in events
                if e["type"] == "role_assigned"
            }
            if roles.get(guest) != ("werewolf" if row["order"] <= 4 else "seer"):
                reasons.append("guest role does not match the frozen cell")
        report = {
            "match_id": record["id"],
            "order": row["order"],
            "status": record["status"],
            "cost_micro_eur": cost,
            "reasons": reasons,
            "models": {m: {"decisions": turns[m], "fallbacks": fallbacks[m]} for m in turns},
        }
        save(
            self.out / f"{row['order']:03d}.json",
            {"record": record, "events": events, "report": report},
        )
        previous = self.state["reports"].get(str(row["order"]))
        self.state["reports"][str(row["order"])] = report
        self.persist()
        if record["status"] == "finished" and (not previous or previous["status"] != "finished"):
            self.say(
                f"{self.job['stage']} table {row['order']} finished: "
                f"EUR {cost / 1_000_000:.6f}; {reasons or 'checks clean'}"
            )
        if reasons:
            # Stop our own ongoing paid activity, never resume/abort/retry it.
            if record["status"] == "running":
                status, _ = self.request("POST", f"/matches/{record['id']}/pause", {})
                if status != 200:
                    raise RunStopped("Safety hold detected; pause failed, check match immediately")
            raise RunStopped("; ".join(reasons))
        return report

    def reviewed_c1_outcome(self):
        """W2 may follow an explicitly reviewed failed C1 diagnostic, never C1 itself."""
        review = self.job.get("reviewed_c1_outcome")
        if review is None:
            return self.smoke_release()
        if (
            not isinstance(review, dict)
            or set(review) != {"match_id", "evidence"}
            or not review["match_id"]
            or not isinstance(review["evidence"], str)
            or not review["evidence"].strip()
        ):
            raise RunStopped("Missing C1 outcome review evidence")
        matches = self.get("/matches?batch=C1")
        found = [m for m in matches if m["id"] == review["match_id"]]
        if (
            len(found) != 1
            or found[0].get("game") != "civ"
            or found[0].get("seed") != 2104001
            or found[0].get("status") not in {"finished", "aborted", "failed", "interrupted"}
        ):
            raise RunStopped("Reviewed C1 outcome is absent or not terminal")

    def smoke_release(self):
        path = self.root / "C1" / "smoke-release.json"
        report_path = self.root / "C1" / "001.json"
        if not path.exists() or not report_path.exists():
            raise RunStopped("C1 first-match review/release required")
        release, report = read_json(path), read_json(report_path)["report"]
        if (
            release.get("report_sha256") != hashlib.sha256(report_path.read_bytes()).hexdigest()
            or release.get("match_id") != report["match_id"]
            or not release.get("evidence")
            or report["status"] != "finished"
            or report["reasons"]
            or report["cost_micro_eur"] > 160_000
        ):
            raise RunStopped("Invalid/stale smoke review release")

    def run(self, *, execute=False, review_evidence=None, pre_start_report=None, arena_build=None):
        if execute and (
            self.job["execution_plan_approved"] is not True
            or not self.job["execution_approval_evidence"]
        ):
            raise RunStopped("Job has no post-review execution approval; dry-run only")
        if execute and not all((review_evidence, pre_start_report, arena_build)):
            raise RunStopped(
                "Execution requires reviewed/merged client evidence, "
                "PR pre-start report and arena build"
            )
        with lock(self.root):
            if not execute:
                quotes = [self.quote(row) for row in self.rows]
                save(
                    self.out / "dry-run.json",
                    {"frozen": self.frozen, "quotes": quotes, "paid_starts": 0},
                )
                return "dry-run"
            self.state.update(
                review_evidence=review_evidence,
                pre_start_report=pre_start_report,
                arena_build=arena_build,
                client_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                job=self.job,
            )
            self.persist()
            final_quotes = [self.quote(row) for row in self.rows]
            if sum(q["estimate_micro_eur"] for q in final_quotes) > self.job["budget_micro_eur"]:
                raise RunStopped("Full schedule estimate exceeds stage envelope")
            self.state["preflight_quotes"] = final_quotes
            self.persist()
            while True:
                history, spent = self.history()
                self.state["spent_micro_eur"] = spent
                self.persist()
                # Re-read every earlier outcome on resume: no cleared stop by editing a local flag.
                for order, record in sorted(history.items()):
                    self.observe(self.rows[order - 1], record)
                active = [r for r in history.values() if r["status"] == "running"]
                if len(active) > 1:
                    raise RunStopped("Multiple active batch matches; reconcile before continuing")
                if active:
                    self.sleep(5)
                    continue
                if len(history) == len(self.rows):
                    self.say(
                        f"{self.job['stage']} ended: {len(history)} finished, "
                        f"EUR {spent / 1_000_000:.6f}"
                    )
                    return "finished"
                order = next(i for i in range(1, len(self.rows) + 1) if i not in history)
                if any(i not in history for i in range(1, order)):
                    raise RunStopped("Gap in schedule")
                if self.job["requires_c1_smoke"]:
                    self.reviewed_c1_outcome()
                if self.job["smoke"] and order > 1:
                    self.smoke_release()
                if (self.root / "DRAIN").exists():
                    return "drained"
                if self.get("/matches?status=running"):
                    raise RunStopped("Another match is running; serial research only")
                row = self.rows[order - 1]
                quote = self.quote(row)
                month = self.get("/ledger/month")["spent_micro_eur"]
                start_allowed(spent, quote["estimate_micro_eur"], self.job, month)
                setup = self.get("/setup")
                if (
                    setup["caps"]["month_eur"] != 25
                    or setup["caps"]["match_eur"] < self.job["match_micro_eur"] / 1_000_000
                ):
                    raise RunStopped("Unexpected effective server caps")
                intent = {
                    "body": self.body(row),
                    "estimate_micro_eur": quote["estimate_micro_eur"],
                    "effective_limit_micro_eur": quote["cap_micro_eur"],
                    "month_before_micro_eur": month,
                    "arena_build": arena_build,
                    "requested_at": datetime.now(UTC).isoformat(),
                    "wait_deadline_epoch": self.now() + self.max_wait_seconds,
                    "setup_caps": setup["caps"],
                    "match_id": None,
                }
                self.state["intents"][str(order)] = intent
                # Crash or HTTP timeout after this => hold/reconcile, never repeat POST.
                self.persist()
                body = {
                    **intent["body"],
                    "confirm_spend": True,
                    "batch": {
                        "id": self.job["batch"],
                        "label": f"{self.job['stage']} explicit tables",
                        "index": order,
                        "of": len(self.rows),
                        "budget_eur": self.job["budget_micro_eur"] / 1_000_000,
                    },
                }
                status, record = self.request("POST", "/matches", body)
                if status != 201:
                    raise RunStopped(f"Start refused ({status}); intent retained, no retry")
                self.verify_record(record, row)
                intent["match_id"] = record["id"]
                self.persist()
                self.say(f"{self.job['stage']} table {order} started: {record['id']}")
                self.sleep(5)

    def quote(self, row):
        if self.job["guest_price_ceilings"]:
            catalog = self.get("/models/catalog")
            if not catalog.get("fresh"):
                raise RunStopped("Catalog price snapshot is stale")
            for model, ceiling in self.job["guest_price_ceilings"].items():
                entries = [m for m in catalog["models"] if m["id"] == model]
                if len(entries) != 1 or any(
                    entries[0][field] is None or entries[0][field] > ceiling[field]
                    for field in ("input_usd_per_mtok", "output_usd_per_mtok")
                ):
                    raise RunStopped("Missing guest or catalog price above frozen plan")
        body = {k: row[k] for k in ("game", "models", "settings")}
        status, quote = self.request("POST", "/matches/estimate", body)
        if (
            status != 200
            or quote.get("cap_micro_eur") != self.job["match_micro_eur"]
            or not quote.get("fits")
        ):
            raise RunStopped("Free estimate refused or effective limit does not match")
        estimate = quote["estimate_micro_eur"]
        if not 0 < estimate < 400_000 or estimate * 4 > row["estimate_micro_eur"] * 5:
            raise RunStopped("Estimate above EUR0.40 or >25% above frozen quote")
        return quote


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("job", type=Path)
    parser.add_argument("--api", default="http://127.0.0.1:8100")
    parser.add_argument("--execute", action="store_true", help="paid; omitted means estimates only")
    parser.add_argument("--review-evidence")
    parser.add_argument("--pre-start-report")
    parser.add_argument("--arena-build")
    args = parser.parse_args()
    # One canonical journal/lock per host, across worktrees and invocations.
    # Never expose an output-directory option that could erase a pending POST.
    root = (
        Path(os.environ.get("LOCALAPPDATA", str(Path.home() / ".local/share")))
        / "AIGameVersus/research-tables"
    )
    try:
        result = Tables(args.job, root, http_request(args.api)).run(
            execute=args.execute,
            review_evidence=args.review_evidence,
            pre_start_report=args.pre_start_report,
            arena_build=args.arena_build,
        )
        print(result)
    except (RunStopped, OSError, ValueError, KeyError) as error:
        print(f"HOLD: {error}")
        raise SystemExit(2) from error


if __name__ == "__main__":
    main()
