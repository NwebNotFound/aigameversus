"""A balance sweep of Throne of Tokens with random bots: no model, no cost.

    uv run python -m arena.research.civ_balance --seeds 20 > sweep.json
    uv run python -m arena.research.civ_balance --seeds 20 --markdown

Every table plays seeded random-bot matches and reads the numbers from the event logs
only: how matches end, whether a seat (and so its start position) is favoured, how long
they last, how many orders are dropped, how often the gold countdown starts, and how
far apart the nations end up. The random bot neither declares war nor attacks
(games/civ/bot.py), so the sweep measures the economy, settling and the barbarians,
not wars between nations.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
from collections import Counter
from collections.abc import Iterable, Sequence
from typing import Any

from arena.agents.random_bot import random_bots
from arena.engine.match import Match
from arena.engine.types import Event
from games.civ.plugin import CivGame

NATIONS = (4, 5, 6)
LENGTHS = (60, 20)  # the full match and the C1 pilot's setting


def play(nations: int, rounds: int, seed: int) -> dict[str, Any]:
    """One bot match, summed up from its log."""
    plugin = CivGame()
    players = [f"p{seat}" for seat in range(1, nations + 1)]
    settings = {} if rounds == 60 else {"rounds": rounds}
    match = Match(plugin, random_bots(plugin, players, seed), seed=seed, settings=settings)
    asyncio.run(match.run())
    return summarize(match.events, players, match.state)


def summarize(events: Sequence[Event], players: Sequence[str], state: Any) -> dict[str, Any]:
    won = next(e for e in events if e.type == "victory").data
    orders = sum(
        len(e.data["arguments"].get("orders", []))
        for e in events
        if e.type in ("action_accepted", "action_fallback") and e.data.get("arguments")
    )
    refused = sum(1 for e in events if e.type == "order_refused")
    countdown = [e.data["rounds"] for e in events if e.type == "economy_countdown"]
    cities = Counter(c.owner for c in state.cities)
    alive = [p for p in players if cities[p] or any(a.owner == p for a in state.armies)]
    scores = sorted((s["score"] for s in won["standings"]), reverse=True)
    return {
        "nations": len(players),
        "kind": won["kind"],
        "rounds": won["round"],
        "rank_by_seat": {p["player"]: p["rank"] for p in won["placements"]},
        "scarce_by_seat": {start.player: start.scarce for start in state.world.starts},
        "orders": orders,
        "refused": refused,
        "countdown_started": any(any(n for n in c.values()) for c in countdown),
        "countdown_best": max((max(c.values()) for c in countdown), default=0),
        "cities_by_seat": {p: cities[p] for p in players},
        "neutral_cities": cities["neutral"],
        "eliminated": len(players) - len(alive),
        "score_gap": scores[0] - scores[1] if len(scores) > 1 else 0,
        "top_score": scores[0],
        "barbarian_conquests": sum(
            1 for e in events if e.type == "city_conquered" and e.data["to"] == "neutral"
        ),
    }


def table(results: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """The numbers of one table (nations x length) over its seeds."""
    rows = list(results)
    n = len(rows)
    seats = [f"p{s}" for s in range(1, rows[0]["nations"] + 1)]
    kinds = Counter(r["kind"] for r in rows)
    orders = sum(r["orders"] for r in rows)
    return {
        "matches": n,
        "victory": {k: kinds.get(k, 0) for k in ("round_limit", "domination", "economy")},
        "rounds_mean": round(statistics.mean(r["rounds"] for r in rows), 1),
        "rank_mean_by_seat": {
            s: round(statistics.mean(r["rank_by_seat"][s] for r in rows), 2) for s in seats
        },
        "wins_by_seat": {s: sum(1 for r in rows if r["rank_by_seat"][s] == 1) for s in seats},
        "rank_mean_by_scarce": _rank_by_scarce(rows),
        "cities_mean_by_seat": {
            s: round(statistics.mean(r["cities_by_seat"][s] for r in rows), 2) for s in seats
        },
        "dropped_share": round(sum(r["refused"] for r in rows) / orders, 3) if orders else None,
        "countdown_reached": sum(1 for r in rows if r["countdown_started"]),
        "countdown_best": max(r["countdown_best"] for r in rows),
        "eliminated_mean": round(statistics.mean(r["eliminated"] for r in rows), 2),
        "neutral_cities_mean": round(statistics.mean(r["neutral_cities"] for r in rows), 2),
        "barbarian_conquests_mean": round(
            statistics.mean(r["barbarian_conquests"] for r in rows), 2
        ),
        "score_gap_median": statistics.median(r["score_gap"] for r in rows),
        "top_score_median": statistics.median(r["top_score"] for r in rows),
    }


def _rank_by_scarce(rows: list[dict[str, Any]]) -> dict[str, float]:
    """A start region is short of one resource: the mean rank of the nations short of each."""
    ranks: dict[str, list[int]] = {}
    for r in rows:
        for seat, scarce in r["scarce_by_seat"].items():
            ranks.setdefault(scarce, []).append(r["rank_by_seat"][seat])
    return {k: round(statistics.mean(v), 2) for k, v in sorted(ranks.items())}


def sweep(seeds: int, nations: Iterable[int] = NATIONS, lengths: Iterable[int] = LENGTHS):
    """Every table, keyed "<nations>x<rounds>", over seeds 1..seeds."""
    return {
        f"{n}x{rounds}": table(play(n, rounds, seed) for seed in range(1, seeds + 1))
        for rounds in lengths
        for n in nations
    }


def markdown(tables: dict[str, dict[str, Any]]) -> str:
    """The sweep as Markdown tables, for the research note."""
    head = (
        "| table | matches | round limit / domination / economy | mean rounds | dropped orders "
        "| countdown reached (best) | eliminated | neutral cities | barbarian conquests "
        "| median score gap 1st-2nd |\n|---|---|---|---|---|---|---|---|---|---|"
    )
    lines = [head]
    for key, t in tables.items():
        v = t["victory"]
        lines.append(
            f"| {key} | {t['matches']} | {v['round_limit']} / {v['domination']} / {v['economy']} "
            f"| {t['rounds_mean']} | {t['dropped_share']:.1%} "
            f"| {t['countdown_reached']} ({t['countdown_best']}) | {t['eliminated_mean']} "
            f"| {t['neutral_cities_mean']} | {t['barbarian_conquests_mean']} "
            f"| {t['score_gap_median']} |"
        )
    lines += ["", "| table | seat | mean rank | wins | mean cities |", "|---|---|---|---|---|"]
    for key, t in tables.items():
        for seat, rank in t["rank_mean_by_seat"].items():
            lines.append(
                f"| {key} | {seat} | {rank} | {t['wins_by_seat'][seat]} "
                f"| {t['cities_mean_by_seat'][seat]} |"
            )
    lines += ["", "| table | start region short of | mean rank |", "|---|---|---|"]
    for key, t in tables.items():
        for scarce, rank in t["rank_mean_by_scarce"].items():
            lines.append(f"| {key} | {scarce} | {rank} |")
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seeds", type=int, default=20)
    parser.add_argument("--markdown", action="store_true", help="tables instead of JSON")
    args = parser.parse_args(argv)
    tables = sweep(args.seeds)
    sys.stdout.write(markdown(tables) if args.markdown else json.dumps(tables, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
