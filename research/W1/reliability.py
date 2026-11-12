import json
from collections import Counter, defaultdict
from pathlib import Path

repo = Path(__file__).resolve().parents[2]
run = repo / "runs/W1-P1"
summary = defaultdict(Counter)
errors = defaultdict(Counter)
match_ids = set()
total = 0
for f in sorted(run.glob("[0-9]*.json")):
    x = json.loads(f.read_text(encoding="utf-8"))
    r = x["record"]
    total += x["cost"]["total_micro_eur"]
    match_ids.add(r["id"])
    seats = r["seats"]
    seen = set()
    for s in seats.values():
        m = s["model_id"]
        summary[m]["seat_matches"] += 1
        seen.add(m)
    for m in seen:
        summary[m]["distinct_matches"] += 1
    failed = set()
    for e in x["events"]:
        t = e["type"]
        d = e["data"]
        p = d.get("player")
        if p not in seats:
            continue
        m = seats[p]["model_id"]
        if t in ("action_accepted", "action_fallback"):
            summary[m]["turns"] += 1
        if t == "action_fallback":
            summary[m]["fallbacks"] += 1
        if t == "agent_failed":
            failed.add(m)
        if t == "action_rejected":
            summary[m]["rejected_answers"] += 1
            errors[m][d["error"]] += 1
    for m in failed:
        summary[m]["failed_matches"] += 1
out = {
    "scope": "P1 reliability only; no outcomes analysed",
    "matches": len(match_ids),
    "cost_micro_eur": total,
    "models": {},
    "errors": errors,
}
for m, s in summary.items():
    for key in ("fallbacks", "failed_matches", "rejected_answers"):
        s.setdefault(key, 0)
    s["fallback_share"] = s["fallbacks"] / s["turns"] if s["turns"] else None
    out["models"][m] = dict(s)
out["gate_pass"] = all(
    s["fallback_share"] <= 0.10 and s["failed_matches"] < 2 for s in summary.values()
)
print(json.dumps(out, indent=2))
dest = repo / "research/W1/P1"
dest.mkdir(parents=True, exist_ok=True)
(dest / "reliability.json").write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
