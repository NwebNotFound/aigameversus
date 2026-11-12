"""GET /insights: what the rated matches say per model, across matches, with intervals."""

from collections import defaultdict
from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from arena.config import load_config
from arena.db.ledger import LedgerUnavailable
from arena.db.reliability import reliabilities
from arena.games import load_games
from arena.ratings import insights
from arena.ratings.insights import Seat
from arena.ratings.store import RatingStore

router = APIRouter(tags=["ratings"])

RELIABILITY_FIELDS = (
    "status",
    "reason",
    "n",
    "matches",
    "fallback_share",
    "cutoff_share",
    "rate_limits_per_move",
    "rejected_rate",
    "warnings",
)


async def _seats(pool, game: str | None, demo: bool) -> tuple[list[Seat], dict[Any, str]]:
    rows = await pool.fetch(
        "SELECT mp.match_id, rm.game_id, mp.rank, mp.players, mp.profile_id, p.model_id, p.name "
        "FROM match_placements mp JOIN rated_matches rm ON rm.match_id = mp.match_id "
        "JOIN player_profiles p ON p.id = mp.profile_id "
        "WHERE ($1::text IS NULL OR rm.game_id = $1) AND ($2 OR NOT p.is_demo) "
        "ORDER BY rm.rated_at, mp.match_id, mp.rank",
        game,
        demo,
    )
    seats = [
        Seat(r["match_id"], r["game_id"], r["model_id"], r["name"], r["rank"], r["players"])
        for r in rows
    ]
    return seats, {r["profile_id"]: r["model_id"] for r in rows}


@router.get("/insights")
async def get_insights(request: Request, game: str | None = None, demo: bool = False) -> dict:
    """Per model across its rated matches of `game` (every game without it):

    - `models`: matches, wins, `win_rate` and `placement_score` (1 = first, 0 = last) with
      95 % intervals from resampling whole matches; `cost_per_match_micro_eur` from the
      ledger (null while it cannot be read); `reliability` from the arena's own logs (fallback,
      cut-off and refusal shares, every game). `provisional` below 10 matches.
    - `head_to_head`: every pair that met, how often each placed above the other, one result
      per match, with a Wilson interval on `a`'s share of the decided matches.

    Free, spoiler-free (finished, rated matches only) and read-only. Demo profiles only with
    `demo=true`.
    """
    pool = request.app.state.pool
    live = request.app.state.live
    if game is not None and game not in load_games():
        raise HTTPException(404, f"No game {game}")
    seats, model_of = await _seats(pool, game, demo)
    models = insights.per_model(seats)
    cost: dict[str, int] = defaultdict(int)
    costs_known = True
    try:
        usage = await RatingStore(pool).usage(live.ledger, game)
    except LedgerUnavailable:
        usage, costs_known = {}, False
    for profile_id, used in usage.items():
        if profile_id in model_of and used.cost_micro_eur is not None:
            cost[model_of[profile_id]] += used.cost_micro_eur
        elif profile_id in model_of:
            costs_known = False
    verdicts = await reliabilities(pool, [m["model_id"] for m in models], load_config().reliability)
    for row in models:
        model = row["model_id"]
        row["cost_per_match_micro_eur"] = (
            round(cost[model] / row["matches"]) if costs_known and row["matches"] else None
        )
        verdict = asdict(verdicts[model])
        row["reliability"] = {k: verdict[k] for k in RELIABILITY_FIELDS}
    return {
        "insights_version": insights.VERSION,
        "game": game,
        "matches": len({s.match_id for s in seats}),
        "min_matches": insights.MIN_MATCHES,
        "method": {
            "interval": f"{int(insights.LEVEL * 100)} % percentile interval of "
            f"{insights.RESAMPLES} resamples of whole matches, seeded",
            "placement_score": "(players - rank) / (players - 1): 1 for first, 0 for last",
            "head_to_head": "one result per match: the better mean rank of a model's seats; "
            "Wilson interval on the decided matches",
        },
        "models": models,
        "head_to_head": insights.head_to_head(seats),
    }
