"""How a Throne of Tokens match is won: domination, economy or the round limit's score.

The numbers are in ``data/victory.yaml``. ``check`` is the last step of a round
(after the events): it moves every nation's economic countdown on, which all
nations see, and declares the winner of the first condition that is met:

- Domination: once the world has ``min_cities_per_nation`` cities per nation, a
  nation holds at least ``city_share`` of all cities and more than
  any other nation (two nations with one city each have not dominated anything).
- Economy: a nation has held at least ``gold`` for ``hold_rounds`` rounds in a row.
- Round limit: after ``rounds`` rounds the highest score wins; equal scores share.

``standings`` ranks the nations by score for the placements of any ending.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from arena.engine.plugin import TurnContext
from games.civ.data_loader import CivData
from games.civ.state import CivState


def round_limit(state: CivState, data: CivData) -> int:
    """The last round of this match: the setting `rounds`, else the data's limit."""
    return state.round_limit or data.victory.round_limit.rounds


def score(state: CivState, data: CivData, player: str) -> int:
    rules = data.victory.round_limit.score
    cities = [city for city in state.cities if city.owner == player]
    nation = state.nations[player]
    return (
        len(cities) * rules.per_city
        + sum(city.population for city in cities) * rules.per_population
        + nation.stock["gold"] // rules.gold_divisor
        + nation.reputation // rules.reputation_divisor
    )


def standings(state: CivState, data: CivData) -> list[dict[str, Any]]:
    """Every nation with its score and rank, best first; equal scores share a rank."""
    scores = {player: score(state, data, player) for player in state.nations}
    order = sorted(scores, key=lambda p: (-scores[p], list(state.nations).index(p)))
    ranked = []
    for player in order:
        rank = 1 + sum(1 for other in scores if scores[other] > scores[player])
        ranked.append({"player": player, "score": scores[player], "rank": rank})
    return ranked


def domination_open(state: CivState, data: CivData) -> bool:
    """Whether the world has enough cities for a domination to count (D-137)."""
    least = data.victory.domination.min_cities_per_nation * len(state.nations)
    return bool(state.cities) and len(state.cities) >= least


def dominating(state: CivState, data: CivData) -> str | None:
    if not domination_open(state, data):
        return None
    total = len(state.cities)
    held = {p: sum(1 for c in state.cities if c.owner == p) for p in state.nations}
    share = data.victory.domination.city_share
    leaders = [
        p
        for p, n in held.items()
        if n / total >= share and all(n > m for q, m in held.items() if q != p)
    ]
    return leaders[0] if leaders else None


def check(state: CivState, data: CivData, ctx: TurnContext) -> str | None:
    """Move the economic countdown on and declare a victory if one is met. Returns its kind."""
    if state.victory is not None:
        return state.victory["kind"]
    rules = data.victory.economy
    counting = {
        player: (state.rich_rounds.get(player, 0) + 1) if nation.stock["gold"] >= rules.gold else 0
        for player, nation in state.nations.items()
    }
    if counting != {p: state.rich_rounds.get(p, 0) for p in state.nations}:
        ctx.emit(
            "economy_countdown",
            {"rounds": counting, "needed": rules.hold_rounds},
            visible_to=None if rules.public_countdown else [],
        )
    rich = [p for p, n in counting.items() if n >= rules.hold_rounds]
    if (winner := dominating(state, data)) is not None:
        return _declare(state, data, ctx, "domination", [winner])
    if rich:
        return _declare(state, data, ctx, "economy", sorted(rich, key=list(state.nations).index))
    if state.round >= round_limit(state, data):
        ranked = standings(state, data)
        return _declare(
            state, data, ctx, "round_limit", [r["player"] for r in ranked if r["rank"] == 1]
        )
    return None


def _declare(
    state: CivState, data: CivData, ctx: TurnContext, kind: str, winners: list[str]
) -> str:
    ranked = standings(state, data)
    # The winners share rank 1; the others follow by score from rank 2, equal scores sharing.
    others = [r for r in ranked if r["player"] not in winners]
    placements = [{"player": p, "rank": 1} for p in winners] + [
        {"player": r["player"], "rank": 2 + sum(1 for o in others if o["score"] > r["score"])}
        for r in others
    ]
    ctx.emit(
        "victory",
        {
            "kind": kind,
            "winners": winners,
            "round": state.round,
            "standings": ranked,
            "placements": placements,
        },
    )
    return kind


# --- events -----------------------------------------------------------------


def _economy_countdown(state: CivState, data: dict[str, Any]) -> None:
    state.rich_rounds = dict(data["rounds"])


def _victory(state: CivState, data: dict[str, Any]) -> None:
    state.victory = {
        "kind": data["kind"],
        "winners": list(data["winners"]),
        "placements": data["placements"],
    }


APPLIERS: dict[str, Callable[[CivState, dict[str, Any]], None]] = {
    "economy_countdown": _economy_countdown,
    "victory": _victory,
}
