"""Descriptive W1 counters and exact seating twins; no model calls or inferred intent."""

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path


def rates(counts):
    counts = dict(counts)
    turns = counts.get("turns", 0)
    counts["fallback_share"] = counts.get("fallbacks", 0) / turns if turns else None
    counts["word_limit_rejections_per_decision"] = (
        counts.get("word_limit_rejections", 0) / turns if turns else None
    )
    return counts


def reliability(events, seats):
    stats = {model: Counter() for model in seats.values()}
    for event in events:
        data, kind = event["data"], event["type"]
        if data.get("player") not in seats:
            continue
        row = stats[seats[data["player"]]]
        if kind in ("action_accepted", "action_fallback"):
            row["turns"] += 1
        if kind == "action_fallback":
            row["fallbacks"] += 1
            row[f"fallback_{data.get('reason', 'unknown')}"] += 1
        if kind == "agent_failed":
            row["failed_agents"] += 1
        if kind == "action_rejected":
            row["rejected_answers"] += 1
            error = data.get("error", "")
            if error.startswith("Your text has "):
                row["word_limit_rejections"] += 1
            elif "cut off at the length limit" in error:
                row["cutoffs"] += 1
            else:
                row["other_rejections"] += 1
    return stats


def twin_key(row):
    return row["seed"], row["seating"], tuple(sorted(row["seats"].items()))


def paired_reliability(baseline, revised):
    left = {twin_key(row): row for row in baseline}
    pairs = []
    totals = {"P1": Counter(), "P3": Counter()}
    for row in revised:
        key = twin_key(row)
        if key not in left:
            raise ValueError("revised match has no identical seed/seating/roster twin")
        before = left[key]
        a = reliability(before["events"], before["seats"])["llama-scout"]
        b = reliability(row["events"], row["seats"])["llama-scout"]
        totals["P1"].update(a)
        totals["P3"].update(b)
        pairs.append(
            {
                "seed": row["seed"],
                "seating": row["seating"],
                "p1_match": before["record"]["id"],
                "p3_match": row["record"]["id"],
                "P1_llama": rates(a),
                "P3_llama": rates(b),
            }
        )
    return {
        "pairs": pairs,
        "missing_baseline_cells": len(baseline) - len(pairs),
        "pooled_paired_llama": {stage: rates(c) for stage, c in totals.items()},
    }


def outcomes(row):
    """Classic-team outcomes/vote accuracy only; no speech semantics inferred."""
    roles = {
        e["data"]["player"]: e["data"]["role"]
        for e in row["events"]
        if e["type"] == "role_assigned"
    }
    winners = {r["player"] for r in row["record"].get("placements", []) if r["rank"] == 1}
    wolf_winners = any(roles.get(p) == "werewolf" for p in winners)
    village_winners = any(roles.get(p) != "werewolf" for p in winners)
    team = "wolves" if wolf_winners and not village_winners else "village"
    if not winners or (wolf_winners and village_winners):
        team = "unknown"
    role_rows = []
    for seat, model in row["seats"].items():
        role_rows.append({"model": model, "role": roles[seat], "won": int(seat in winners)})
    votes = Counter()
    last_action = {}
    for event in row["events"]:
        data, kind = event["data"], event["type"]
        player = data.get("player")
        if kind in ("action_accepted", "action_fallback"):
            last_action[player] = kind
        if kind == "vote_cast" and roles.get(player) != "werewolf":
            prefix = "bot" if last_action.get(player) == "action_fallback" else "model"
            if data.get("target") is None:
                votes[f"{prefix}_village_abstentions"] += 1
            else:
                votes[f"{prefix}_village_votes"] += 1
                votes[f"{prefix}_votes_on_wolf"] += roles.get(data["target"]) == "werewolf"
    return team, role_rows, votes


def load_stage(root, stage):
    folder = root / f"W1-{stage}"
    lines = [json.loads(line) for line in (folder / "runs.jsonl").read_text().splitlines()]
    last = {row["order"]: row for row in lines}
    rows = []
    for order, line in sorted(last.items()):
        if line["status"] != "finished":
            continue
        attempt = line["attempt"]
        suffix = "" if attempt == 1 else f"-attempt{attempt}"
        saved = json.loads((folder / f"{order:03d}{suffix}.json").read_text(encoding="utf-8"))
        rows.append(
            {
                **saved,
                "seed": line["seed"],
                "seating": line["seating"],
                "seats": {p: s["model"] for p, s in line["seats"].items()},
            }
        )
    return rows, sum(line["cost_micro_eur"] for line in lines)


def analyse(root):
    result = {
        "stages": {},
        "limitations": [
            "One scenario seed per stage; descriptive cells, not independent seed replications.",
            "P1/P3 builds and cost caps differ; no isolated causal prompt effect claimed.",
            "P3 lacks two budget-stopped cells; single-match P2 supports no general inference.",
        ],
    }
    stages = {}
    for stage in ("P1", "P2", "P3"):
        rows, cost = load_stage(root, stage)
        stages[stage] = rows
        stats, teams, roles, votes = (
            defaultdict(Counter),
            Counter(),
            defaultdict(Counter),
            Counter(),
        )
        for row in rows:
            one = reliability(row["events"], row["seats"])
            for model, counts in one.items():
                stats[model].update(counts)
                stats[model]["distinct_matches"] += 1
                stats[model]["seat_appearances"] += list(row["seats"].values()).count(model)
            team, role_rows, v = outcomes(row)
            teams[team] += 1
            votes.update(v)
            for label in role_rows:
                key = f"{label['model']}/{label['role']}"
                roles[key]["appearances"] += 1
                roles[key]["wins"] += label["won"]
        result["stages"][stage] = {
            "matches": len(rows),
            "cost_micro_eur": cost,
            "models": {m: rates(c) for m, c in stats.items()},
            "team_wins": dict(teams),
            "role_results": dict(roles),
            "votes": dict(votes),
            "without_llama_seat_records": {
                m: rates(c) for m, c in stats.items() if m != "llama-scout"
            },
            "whole_match_llama_exclusion_remaining": sum(
                "llama-scout" not in r["seats"].values() for r in rows
            ),
        }
    result["paired_reliability"] = paired_reliability(stages["P1"], stages["P3"])
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("runs", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    result = analyse(args.runs)
    (args.out / "results.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                stage: {"matches": row["matches"], "cost_micro_eur": row["cost_micro_eur"]}
                for stage, row in result["stages"].items()
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
