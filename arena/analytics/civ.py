"""Throne of Tokens analytics: per nation and round, battles, diplomacy, orders, decisions.

    analyze(log, spoilers)   # log: (seq, event) pairs, as arena.analytics passes them

With spoilers the game events are applied to a fresh state in order, as a replay does,
and every nation's numbers are read at the end of each round (`series`). Most events
of the game are private to one nation, so without spoilers a state rebuilt from the
public events would be wrong: `series`, `battles`, `orders`, `decisions` and
`behaviour` are null then, and only what every nation saw remains (conquests, wars
and treaties, the gold countdown, public talk, the final standings).
docs/METRICS.md defines every number; `analytics_version` changes when the shape does.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any

from arena.analytics.liars_deck import rate
from arena.engine.replay import plugin_for, recorded_version
from arena.engine.types import MESSAGE, Event, EventSource
from games.civ import combat, victory
from games.civ.plugin import CivGame
from games.civ.state import NEUTRAL, CivState

VERSION = "civ/1"
RESOURCES = ("food", "wood", "iron", "gold")
TOP_REASONS = 5  # most frequent kinds of dropped orders listed per nation
# Behaviour tags (spoilers only): rule-based, the thresholds documented in docs/METRICS.md.
AGGRESSOR_ATTACKS = 3  # attacks on other nations (or one declared war)
TURTLE_FORTIFIES = 5  # fortify orders with no war and no attack ...
TURTLE_WALLS = 2  # ... or this many walls built
TRADER_TRADES = 2  # trades agreed

Log = list[tuple[int, Event]]


def analyze(log: Log, spoilers: bool) -> dict[str, Any]:
    events = [e for _, e in log]
    start = next((e for e in events if e.type == "match_started"), None)
    players = list(start.data["players"]) if start else []
    settings = dict(start.data.get("settings") or {}) if start else {}
    # The rules the match was played with, not the newest (D-139).
    plugin = plugin_for(CivGame(), start) if start else CivGame()
    meta = {
        "version": recorded_version(start) if start else None,
        "prompt_version": start.data.get("prompt_version") if start else None,
        "seed": start.data.get("seed") if start else None,  # not in the spoiler-free start
        "settings": settings,
        "rounds_total": settings.get("rounds", plugin.data.victory.round_limit.rounds),
    }
    built = _replay(log, players, settings, plugin) if spoilers and start else None
    return {
        "meta": meta,
        "analytics_version": VERSION,
        "nations": players,
        "series": built["series"] if built else None,
        "victory": _victory(events, built),
        "battles": built["battles"] if built else None,
        "conquests": _conquests(log),
        "diplomacy": _diplomacy(log, players, spoilers),
        "orders": _orders(log, players) if spoilers else None,
        "decisions": _decisions(events, players) if spoilers else None,
        "behaviour": _behaviour(log, players, built) if built else None,
    }


# --- the state, round by round (spoilers only) ------------------------------------------------


def _replay(log: Log, players: list[str], settings: dict[str, Any], plugin: CivGame):
    """Apply the game events in order; read every nation at the end of each round."""
    game_settings = {k: v for k, v in settings.items() if k == "rounds"}
    state = plugin.initial_state(players, game_settings)
    rows: list[dict[str, Any]] = []
    income: dict[str, Counter] = {p: Counter() for p in players}
    battles: list[dict[str, Any]] = []
    attacks = Counter()  # attacks ordered on a tile another nation held, per nation
    fortifies = Counter()
    walls = Counter()
    for seq, event in log:
        if event.source is not EventSource.GAME:
            continue
        if event.type == "round_started" and state.round >= 1:
            rows.append(_snapshot(state, plugin, players, income))
            income = {p: Counter() for p in players}
        if event.type == "production":
            income[event.data["player"]].update(event.data["yields"])
        elif event.type == "battle":
            battles.append({"seq": seq, **event.data})
        elif event.type == "attack_ordered":
            army = next((a for a in state.armies if a.id == event.data["army"]), None)
            if army is not None:
                held = combat.holder(state, tuple(event.data["target"]), army.owner)
                if held is not None and held != NEUTRAL and army.owner != NEUTRAL:
                    attacks[army.owner] += 1
        elif event.type == "army_fortified":
            fortifies[state.army(event.data["army"]).owner] += 1
        elif event.type == "building_completed" and event.data["building"] == "wall":
            walls[state.city(event.data["city"]).owner] += 1
        plugin.apply_event(state, event)
    if state.round >= 1:
        rows.append(_snapshot(state, plugin, players, income))
    series = {
        "rounds": [row["round"] for row in rows],
        "nations": {
            p: {key: [row["nations"][p][key] for row in rows] for key in _NATION_KEYS}
            for p in players
        },
        "progress": {key: [row["progress"][key] for row in rows] for key in _PROGRESS_KEYS},
    }
    return {
        "series": series,
        "battles": battles,
        "counts": {"attacks": attacks, "fortifies": fortifies, "walls": walls},
    }


_NATION_KEYS = (
    "stock",
    "income",
    "cities",
    "population",
    "armies",
    "units",
    "strength",
    "score",
    "reputation",
    "at_war",
)
_PROGRESS_KEYS = ("cities_total", "domination_needed", "leader", "leader_cities", "gold_countdown")


def _snapshot(
    state: CivState, plugin: CivGame, players: list[str], income: dict[str, Counter]
) -> dict[str, Any]:
    data = plugin.data
    nations = {}
    for p in players:
        cities = [c for c in state.cities if c.owner == p]
        armies = [a for a in state.armies if a.owner == p]
        nations[p] = {
            "stock": dict(state.nations[p].stock),
            "income": {r: income[p].get(r, 0) for r in RESOURCES},
            "cities": len(cities),
            "population": sum(c.population for c in cities),
            "armies": len(armies),
            "units": sum(len(a.units) for a in armies),
            "strength": sum(combat.strength(data, a.units) for a in armies),
            "score": victory.score(state, data, p),
            "reputation": state.nations[p].reputation,
            "at_war": sorted(q for pair in state.wars if p in pair for q in pair if q != p),
        }
    held = {p: nations[p]["cities"] for p in players}
    leader = max(players, key=lambda p: (held[p], -players.index(p))) if players else None
    total = len(state.cities)
    rich = {p: n for p, n in state.rich_rounds.items() if n}
    holder = max(rich, key=lambda p: (rich[p], -players.index(p))) if rich else None
    return {
        "round": state.round,
        "nations": nations,
        "progress": {
            "cities_total": total,
            "domination_needed": max(
                1, math.ceil(data.victory.domination.city_share * total - 1e-9)
            ),
            "leader": leader,
            "leader_cities": held[leader] if leader else 0,
            "gold_countdown": None
            if holder is None
            else {"nation": holder, "rounds_held": rich[holder]},
        },
    }


# --- public parts ----------------------------------------------------------------------------


def _victory(events: list[Event], built: dict[str, Any] | None) -> dict[str, Any]:
    """How the match ended (null while it runs), and the public countdown, round by round."""
    won = next((e.data for e in events if e.type == "victory"), None)
    countdown = [
        {
            "round": _round_of(events, i),
            "rounds": dict(e.data["rounds"]),
            "needed": e.data["needed"],
        }
        for i, e in enumerate(events)
        if e.type == "economy_countdown"
    ]
    return {
        "kind": won["kind"] if won else None,
        "winners": list(won["winners"]) if won else None,
        "round": won["round"] if won else None,
        "standings": won["standings"] if won else None,
        "countdown": countdown,
    }


def _round_of(events: list[Event], index: int) -> int:
    """The round an event belongs to: that of the last round_started before it."""
    for e in reversed(events[:index]):
        if e.type == "round_started":
            return e.data["round"]
    return 0


def _conquests(log: Log) -> list[dict[str, Any]]:
    return [
        {
            "seq": seq,
            "round": e.data["round"],
            "city": e.data["city"],
            "from": e.data["from"],
            "to": e.data["to"],
        }
        for seq, e in log
        if e.type == "city_conquered"
    ]


_TIMELINE = ("war_declared", "treaty_signed", "treaty_broken", "treaty_expired")


def _diplomacy(log: Log, players: list[str], spoilers: bool) -> dict[str, Any]:
    """Wars and treaties (public), offers and their answers (spoilers), talk per nation."""
    events = [e for _, e in log]
    hidden = None if not spoilers else 0  # counts that need private events
    per: dict[str, dict[str, Any]] = {
        p: {
            "wars_declared": 0,
            "treaties_signed": 0,
            "treaties_broken": 0,
            "messages_public": 0,
            "messages_private": hidden,
            "offers_sent": hidden,
            "offers_received": hidden,
            "offers_accepted": hidden,
            "offers_declined": hidden,
            "offers_lapsed": hidden,
        }
        for p in players
    }
    timeline = []
    treaty_kinds: dict[str, str] = {}  # treaty id -> kind, for a broken or expired one
    receivers: dict[str, str] = {}  # offer id -> who was asked
    for i, (seq, e) in enumerate(log):
        d = e.data
        if e.type in _TIMELINE:
            if e.type == "treaty_signed":
                treaty_kinds[d["treaty"]] = d["kind"]
            item = {"seq": seq, "round": _round_of(events, i), "event": e.type}
            item |= {
                k: d[k] for k in ("by", "on", "joined", "broken", "treaty", "parties") if k in d
            }
            if "treaty" in d:
                item["treaty_kind"] = treaty_kinds.get(d["treaty"])
            timeline.append(item)
        if e.type == "war_declared" and d["by"] in per:
            per[d["by"]]["wars_declared"] += 1
        elif e.type == "treaty_signed":
            for p in d["parties"]:
                if p in per:
                    per[p]["treaties_signed"] += 1
        elif e.type == "treaty_broken" and d["by"] in per:
            per[d["by"]]["treaties_broken"] += 1
        elif e.type == MESSAGE and d["player"] in per:
            key = "messages_public" if e.visible_to is None else "messages_private"
            if per[d["player"]][key] is not None:
                per[d["player"]][key] += 1
        if not spoilers:
            continue
        if e.type in ("treaty_offered", "trade_offered"):
            receivers[d["offer"]] = d["to"]
            per[d["sender"]]["offers_sent"] += 1
            per[d["to"]]["offers_received"] += 1
        elif d.get("offer") in receivers:
            answered = {
                "treaty_signed": "offers_accepted",
                "trade_agreed": "offers_accepted",
                "treaty_declined": "offers_declined",
                "trade_declined": "offers_declined",
                "offer_lapsed": "offers_lapsed",
            }.get(e.type)
            if answered:
                per[receivers[d["offer"]]][answered] += 1
    return {"timeline": timeline, "by_nation": per}


# --- orders and decisions (spoilers only) ------------------------------------------------------

_IDS = re.compile(r"\b[acotp]\d+\b|\(\d+, \d+\)|\[\d+, \d+\]|\b\d+\b")


def reason_kind(reason: str) -> str:
    """A refusal without its ids and numbers, so refusals of one kind count together."""
    return _IDS.sub("#", reason.split(". ")[0]).strip()


def _orders(log: Log, players: list[str]) -> dict[str, Any]:
    """Orders sent (the model's own and the fallback's apart) and dropped, per nation."""
    per = {
        p: {"submitted": 0, "by_fallback": 0, "dropped": 0, "by_type": {}, "reasons": Counter()}
        for p in players
    }
    for _, e in log:
        if e.type in ("action_accepted", "action_fallback") and e.data.get("player") in per:
            orders = (e.data.get("arguments") or {}).get("orders") or []
            row = per[e.data["player"]]
            key = "by_fallback" if e.type == "action_fallback" else "submitted"
            row[key] += len(orders)
            for order in orders:
                kind = str(order.get("type"))
                row["by_type"].setdefault(kind, {"sent": 0, "dropped": 0})["sent"] += 1
        elif e.type == "order_refused" and e.data["nation"] in per:
            row = per[e.data["nation"]]
            row["dropped"] += 1
            kind = str(e.data["order"].get("type"))
            row["by_type"].setdefault(kind, {"sent": 0, "dropped": 0})["dropped"] += 1
            row["reasons"][f"{kind}: {reason_kind(e.data['reason'])}"] += 1
    for row in per.values():
        sent = row["submitted"] + row["by_fallback"]
        row["dropped_share"] = rate(row["dropped"], sent)
        row["reasons"] = [
            {"reason": reason, "count": n} for reason, n in row["reasons"].most_common(TOP_REASONS)
        ]
    return per


def _decisions(events: list[Event], players: list[str]) -> dict[str, Any]:
    """What each nation's calls took, from the engine's `decision` events (models only)."""
    per = {}
    for p in players:
        mine = [e.data for e in events if e.type == "decision" and e.data.get("player") == p]
        moves = sum(
            1
            for e in events
            if e.type in ("action_accepted", "action_fallback") and e.data.get("player") == p
        )
        fallbacks = sum(
            1 for e in events if e.type == "action_fallback" and e.data.get("player") == p
        )
        rejected = sum(
            1 for e in events if e.type == "action_rejected" and e.data.get("player") == p
        )
        times = [d["latency_ms"] for d in mine if d.get("latency_ms") is not None]
        per[p] = {
            "moves": moves,
            "model_moves": len(mine),  # 0 for a bot: bots leave no decision
            "fallbacks": fallbacks,
            "fallback_share": rate(fallbacks, moves),
            "rejected": rejected,
            "response_ms_total": sum(times) if times else None,
            "response_ms_mean": sum(times) / len(times) if times else None,
            "tokens_in": _total(mine, "tokens_in"),
            "tokens_out": _total(mine, "tokens_out"),
            "reasoning_tokens": _total(mine, "reasoning_tokens"),
            "retries": _total(mine, "retries") or 0,
            "rate_limits": _total(mine, "rate_limits") or 0,
            "cutoffs": _total(mine, "cutoffs") or 0,
        }
    return per


def _total(decisions: list[dict[str, Any]], field: str) -> int | None:
    values = [d[field] for d in decisions if d.get(field) is not None]
    return sum(values) if values else None


def _behaviour(log: Log, players: list[str], built: dict[str, Any]) -> dict[str, Any]:
    """Rule-based tags per nation, with the counts they rest on (docs/METRICS.md)."""
    wars, broken, trades = Counter(), Counter(), Counter()
    offers: dict[str, tuple[str, str]] = {}
    for _, e in log:
        d = e.data
        if e.type == "war_declared":
            wars[d["by"]] += 1
            broken[d["by"]] += len(d.get("broken") or [])
        elif e.type == "treaty_broken":
            broken[d["by"]] += 1
        elif e.type == "trade_offered":
            offers[d["offer"]] = (d["sender"], d["to"])
        elif e.type == "trade_agreed" and d["offer"] in offers:
            for p in offers[d["offer"]]:
                trades[p] += 1
    seen = built["counts"]
    tags = {}
    for p in players:
        c = {
            "wars_declared": wars[p],
            "attacks": seen["attacks"][p],
            "treaties_broken": broken[p],
            "trades": trades[p],
            "fortifies": seen["fortifies"][p],
            "walls": seen["walls"][p],
        }
        mine = []
        if c["wars_declared"] or c["attacks"] >= AGGRESSOR_ATTACKS:
            mine.append("aggressor")
        if c["treaties_broken"]:
            mine.append("betrayer")
        if c["trades"] >= TRADER_TRADES:
            mine.append("trader")
        peaceful = not c["wars_declared"] and not c["attacks"]
        if peaceful and (c["fortifies"] >= TURTLE_FORTIFIES or c["walls"] >= TURTLE_WALLS):
            mine.append("turtle")
        tags[p] = {"tags": mine, "counts": c}
    return tags
