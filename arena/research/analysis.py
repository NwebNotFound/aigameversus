"""The registered analysis of an E1 league stage, from a run folder of the batch runner.

    uv run python -m arena.research.analysis runs/E1-A2 --out research/E1/A2

Written before the stage's outcomes were read (plan E1, version 3). It reads
`runs.jsonl` and the saved match logs, keeps the matches that count (finished,
last attempt per cell, not pilot), and computes:

- H1: permutation test of "all models equally strong". Statistic: sum over
  models of (mean finishing rank - 2.5) squared; null: the ranks shuffled
  among the four seats inside each match.
- H2: per model, exact two-sided binomial test of the win share against 0.25,
  Holm over the models; Wilson 95 % intervals.
- H3: per model, a 2 x 2 table over call opportunities (called or not, facing
  a lie or an honest play); Fisher's exact test per model with Holm, and the
  Mantel-Haenszel odds ratio with its test pooled over the models.
- H4: winners' seats against 1/4 each (chi-square statistic, Monte Carlo p).
- Plackett-Luce strengths (MM algorithm) with bootstrap intervals over whole seeds.
- Reliability per model: clean moves, repaired moves, rejected answers per
  move, fallback moves, failed agents.

Pure standard library; every random draw comes from a seeded generator.
"""

import argparse
import json
import math
import random
import sys
from collections import Counter, defaultdict
from collections.abc import Sequence
from itertools import combinations
from pathlib import Path
from typing import Any

from arena.analytics.liars_deck import analyze
from arena.engine.types import Event

SEED = 20261111  # every permutation and bootstrap derives from this
SEATS = 4


# ---- data -------------------------------------------------------------------------------------


def load_matches(run: Path) -> list[dict[str, Any]]:
    """The matches that count: finished, the last attempt of each cell, no pilot match."""
    last: dict[int, dict] = {}
    for line in (run / "runs.jsonl").read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        last[row["order"]] = row
    matches = []
    for order in sorted(last):
        row = last[order]
        if row["status"] != "finished" or row["pilot"]:
            continue
        name = f"{order:03d}" + ("" if row["attempt"] == 1 else f"-attempt{row['attempt']}")
        saved = json.loads((run / f"{name}.json").read_text(encoding="utf-8"))
        seats = {p: s["model"] for p, s in row["seats"].items()}
        ranks = {p["player"]: p["rank"] for p in row["placements"]}
        matches.append(
            {
                "order": order,
                "table": row["table"],
                "seed": row["seed"],
                "seating": row["seating"],
                "seats": seats,
                "ranks": ranks,
                "seat_reports": row["seats"],
                "events": saved["events"],
                "cost": row["cost_micro_eur"],
            }
        )
    return matches


# ---- small statistics ------------------------------------------------------------------------


def wilson(part: int, whole: int, z: float = 1.96) -> tuple[float, float] | None:
    if whole == 0:
        return None
    p = part / whole
    centre = p + z * z / (2 * whole)
    spread = z * math.sqrt(p * (1 - p) / whole + z * z / (4 * whole * whole))
    denominator = 1 + z * z / whole
    return max((centre - spread) / denominator, 0.0), min((centre + spread) / denominator, 1.0)


def binomial_two_sided(k: int, n: int, p: float) -> float:
    """Exact two-sided p: the sum of all outcomes no more likely than k."""
    pmf = [math.comb(n, i) * p**i * (1 - p) ** (n - i) for i in range(n + 1)]
    return min(1.0, sum(q for q in pmf if q <= pmf[k] * (1 + 1e-9)))


def fisher_two_sided(a: int, b: int, c: int, d: int) -> float:
    """Fisher's exact test of the 2 x 2 table [[a, b], [c, d]], two-sided."""
    row1, col1, n = a + b, a + c, a + b + c + d

    def prob(x: int) -> float:
        return math.comb(col1, x) * math.comb(n - col1, row1 - x) / math.comb(n, row1)

    low, high = max(0, row1 + col1 - n), min(row1, col1)
    observed = prob(a)
    return min(1.0, sum(prob(x) for x in range(low, high + 1) if prob(x) <= observed * (1 + 1e-9)))


def mantel_haenszel(tables: Sequence[tuple[int, int, int, int]]) -> dict[str, float | None]:
    """Pooled odds ratio and the continuity-corrected Cochran-Mantel-Haenszel test."""
    num = den = 0.0
    sum_a = sum_e = sum_v = 0.0
    for a, b, c, d in tables:
        n = a + b + c + d
        if n < 2:
            continue
        num += a * d / n
        den += b * c / n
        row1, col1 = a + b, a + c
        sum_a += a
        sum_e += row1 * col1 / n
        sum_v += row1 * (n - row1) * col1 * (n - col1) / (n * n * (n - 1))
    odds = num / den if den else None
    if not sum_v:
        return {"odds_ratio": odds, "chi2": None, "p": None}
    chi2 = (abs(sum_a - sum_e) - 0.5) ** 2 / sum_v
    return {"odds_ratio": odds, "chi2": chi2, "p": math.erfc(math.sqrt(chi2 / 2))}


def holm(pvalues: dict[str, float]) -> dict[str, float]:
    """Holm-adjusted p-values (monotone, capped at 1)."""
    ordered = sorted(pvalues.items(), key=lambda item: item[1])
    adjusted, running = {}, 0.0
    for i, (name, p) in enumerate(ordered):
        running = max(running, min(1.0, (len(ordered) - i) * p))
        adjusted[name] = running
    return adjusted


# ---- the registered tests --------------------------------------------------------------------


def _rank_statistic(matches: Sequence[dict], ranks_of) -> float:
    total: dict[str, list[int]] = defaultdict(list)
    for match in matches:
        for player, rank in ranks_of(match).items():
            total[match["seats"][player]].append(rank)
    return sum((sum(r) / len(r) - 2.5) ** 2 for r in total.values())


def h1_permutation(matches: Sequence[dict], permutations: int = 100_000) -> dict[str, float]:
    observed = _rank_statistic(matches, lambda m: m["ranks"])
    rng = random.Random(SEED)
    at_least = 0
    for _ in range(permutations):

        def shuffled(match):
            players = list(match["ranks"])
            values = [match["ranks"][p] for p in players]
            rng.shuffle(values)
            return dict(zip(players, values, strict=True))

        if _rank_statistic(matches, shuffled) >= observed - 1e-12:
            at_least += 1
    return {
        "statistic": observed,
        "p": (at_least + 1) / (permutations + 1),
        "permutations": permutations,
    }


def h2_wins(matches: Sequence[dict]) -> dict[str, dict]:
    wins: Counter[str] = Counter()
    played: Counter[str] = Counter()
    for match in matches:
        for player, model in match["seats"].items():
            played[model] += 1
            wins[model] += match["ranks"].get(player) == 1
    raw = {m: binomial_two_sided(wins[m], played[m], 1 / SEATS) for m in played}
    adjusted = holm(raw)
    return {
        m: {
            "wins": wins[m],
            "matches": played[m],
            "share": wins[m] / played[m],
            "wilson95": wilson(wins[m], played[m]),
            "p": raw[m],
            "p_holm": adjusted[m],
        }
        for m in sorted(played)
    }


def call_tables(matches: Sequence[dict]) -> dict[str, list[int]]:
    """Per model [a, b, c, d]: called on a lie, did not call on a lie, called on an honest
    play, did not call on an honest play; over the model's own opportunities (no fallback,
    no automatic call), from the analytics with the hidden cards."""
    tables: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0, 0])
    for match in matches:
        log = [
            (e.get("seq", i), Event(**{k: v for k, v in e.items() if k != "seq"}))
            for i, e in enumerate(match["events"])
        ]
        result = analyze(log, spoilers=True)
        for player, totals in result["totals"].items():
            model = match["seats"][player]
            hit, alarm = totals["hit_rate"], totals["false_alarm_rate"]
            if hit:
                tables[model][0] += hit["n"]
                tables[model][1] += hit["of"] - hit["n"]
            if alarm:
                tables[model][2] += alarm["n"]
                tables[model][3] += alarm["of"] - alarm["n"]
    return dict(tables)


def h3_calls(matches: Sequence[dict]) -> dict[str, Any]:
    tables = call_tables(matches)
    per_model = {}
    raw = {}
    for model, (a, b, c, d) in sorted(tables.items()):
        raw[model] = fisher_two_sided(a, b, c, d)
        odds = (a * d) / (b * c) if b * c else None
        per_model[model] = {
            "table": [a, b, c, d],
            "hit_rate": a / (a + b) if a + b else None,
            "false_alarm_rate": c / (c + d) if c + d else None,
            "odds_ratio": odds,
            "p": raw[model],
        }
    for model, p in holm(raw).items():
        per_model[model]["p_holm"] = p
    pooled = mantel_haenszel([tuple(t) for t in tables.values()])
    return {"per_model": per_model, "pooled": pooled}


def h4_seats(matches: Sequence[dict], draws: int = 100_000) -> dict[str, Any]:
    counts = [0] * SEATS
    for match in matches:
        winner = next(p for p, r in match["ranks"].items() if r == 1)
        counts[int(winner[1:]) - 1] += 1
    n = sum(counts)

    def chi2(observed):
        expected = n / SEATS
        return sum((o - expected) ** 2 / expected for o in observed)

    observed = chi2(counts)
    rng = random.Random(SEED + 4)
    at_least = 0
    for _ in range(draws):
        sample = [0] * SEATS
        for _ in range(n):
            sample[rng.randrange(SEATS)] += 1
        at_least += chi2(sample) >= observed - 1e-12
    return {"wins_by_seat": counts, "chi2": observed, "p": (at_least + 1) / (draws + 1)}


# ---- Plackett-Luce ----------------------------------------------------------------------------


def plackett_luce(rankings: Sequence[Sequence[str]], iterations: int = 500) -> dict[str, float]:
    """Strengths (log scale, mean 0) from full rankings, best first; Hunter's MM algorithm."""
    items = sorted({item for ranking in rankings for item in ranking})
    gamma = dict.fromkeys(items, 1.0)
    wins = Counter(item for ranking in rankings for item in ranking[:-1])
    for _ in range(iterations):
        denominator: dict[str, float] = defaultdict(float)
        for ranking in rankings:
            for j in range(len(ranking) - 1):
                rest = ranking[j:]
                total = sum(gamma[i] for i in rest)
                for i in rest:
                    denominator[i] += 1 / total
        new = {i: (wins[i] or 0.5) / denominator[i] for i in items}
        scale = math.exp(sum(math.log(v) for v in new.values()) / len(new))
        gamma = {i: v / scale for i, v in new.items()}
    return {i: math.log(v) for i, v in gamma.items()}


def _rankings(matches: Sequence[dict]) -> list[list[str]]:
    return [
        [match["seats"][p] for p, _ in sorted(match["ranks"].items(), key=lambda item: item[1])]
        for match in matches
    ]


def strengths_with_bootstrap(matches: Sequence[dict], resamples: int = 2000) -> dict[str, dict]:
    point = plackett_luce(_rankings(matches))
    by_seed: dict[int, list[dict]] = defaultdict(list)
    for match in matches:
        by_seed[match["seed"]].append(match)
    seeds = sorted(by_seed)
    rng = random.Random(SEED + 5)
    draws: dict[str, list[float]] = defaultdict(list)
    for _ in range(resamples):
        sample = [m for _ in seeds for m in by_seed[rng.choice(seeds)]]
        for item, value in plackett_luce(_rankings(sample), iterations=200).items():
            draws[item].append(value)
    out = {}
    for item, value in sorted(point.items(), key=lambda kv: -kv[1]):
        values = sorted(draws[item])
        out[item] = {
            "strength": value,
            "ci95": [values[int(0.025 * len(values))], values[int(0.975 * len(values)) - 1]],
        }
    return out


# ---- reliability ------------------------------------------------------------------------------


def reliability(matches: Sequence[dict]) -> dict[str, dict]:
    rows: dict[str, Counter] = defaultdict(Counter)
    for match in matches:
        repaired: Counter[str] = Counter()
        for event in match["events"]:
            data = event.get("data") or {}
            if event.get("type") == "decision" and data.get("repaired"):
                repaired[data.get("player")] += 1
        for player, seat in match["seat_reports"].items():
            row = rows[seat["model"]]
            row["matches"] += 1
            row["moves"] += seat["turns"]
            row["fallback"] += seat["fallbacks"]
            row["rejected"] += seat["rejected"]
            row["failed_agents"] += seat["agent_failed"]
            row["repaired"] += repaired[player]
    out = {}
    for model, row in sorted(rows.items()):
        moves = row["moves"]
        clean = moves - row["fallback"] - row["repaired"]
        out[model] = {
            "matches": row["matches"],
            "moves": moves,
            "clean_share": clean / moves if moves else None,
            "repaired_share": row["repaired"] / moves if moves else None,
            "rejected_per_move": row["rejected"] / moves if moves else None,
            "fallback_share": row["fallback"] / moves if moves else None,
            "failed_agents": row["failed_agents"],
        }
    return out


def balance(matches: Sequence[dict]) -> dict[str, Any]:
    """How far the played matches are from the full design (per model, per seat, per pair)."""
    per_model = Counter(m for match in matches for m in match["seats"].values())
    per_seat = Counter((model, p) for match in matches for p, model in match["seats"].items())
    pairs = Counter(
        pair for match in matches for pair in combinations(sorted(match["seats"].values()), 2)
    )
    return {
        "matches": len(matches),
        "per_model": dict(sorted(per_model.items())),
        "per_seat_min_max": [min(per_seat.values()), max(per_seat.values())] if per_seat else None,
        "pair_meetings_min_max": [min(pairs.values()), max(pairs.values())] if pairs else None,
    }


def analyse(run: Path, permutations: int = 100_000, resamples: int = 2000) -> dict[str, Any]:
    matches = load_matches(run)
    h1 = h1_permutation(matches, permutations)
    h3 = h3_calls(matches)
    h4 = h4_seats(matches)
    # The four confirmatory tests share one family-wise level (plan: analysis.error_rate).
    family = holm(
        {"H1": h1["p"], "H3_pooled": h3["pooled"]["p"] if h3["pooled"]["p"] is not None else 1.0}
    )
    return {
        "run": str(run),
        "design": balance(matches),
        "cost_eur": sum(m["cost"] for m in matches) / 1e6,
        "H1": {**h1, "p_holm_family": family["H1"]},
        "H2": h2_wins(matches),
        "H3": {**h3, "pooled_p_holm_family": family["H3_pooled"]},
        "H4": h4,
        "plackett_luce": strengths_with_bootstrap(matches, resamples),
        "reliability": reliability(matches),
        "notes": [
            "H5 (stage B) and H6 (stage C) join the family of confirmatory tests when those "
            "stages are played; the Holm adjustment here covers H1 and H3 only so far.",
        ],
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m arena.research.analysis", description=__doc__)
    parser.add_argument("run", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--permutations", type=int, default=100_000)
    parser.add_argument("--resamples", type=int, default=2000)
    args = parser.parse_args(argv)
    result = analyse(args.run, args.permutations, args.resamples)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "results.json").write_text(
        json.dumps(result, indent=1) + "\n", encoding="utf-8", newline="\n"
    )
    print(json.dumps({k: result[k] for k in ("design", "cost_eur")}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
