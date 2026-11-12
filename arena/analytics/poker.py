"""Poker analytics: every hand, every move, the chips of each player, and what they add up to.

Everything here is read from public events (the actions, the board, the showdown, the pots), so
a spoiler-free viewer gets it all, including how a showdown ended: a player who bet or raised and
then lost at the showdown *bluffed* or at least was beaten, one who won it *bet for value*. The
two numbers that need a hand nobody showed (a bluff that won the pot without a showdown, a fold
that would have won) read the hole cards, so they are null without `spoilers`. The definitions
of VPIP, aggression and the bluff hand are those of `arena/stats/poker.py`; a test keeps the
two in step. See docs/METRICS.md.
"""

from typing import Any

from arena.analytics.liars_deck import DECISION_FIELDS, _Decisions, rate
from arena.engine.types import Event, EventSource, PlayerId
from arena.stats import poker as stats
from games.poker.plugin import DEFAULTS

KINDS = ("fold", "check", "call", "raise", "all_in")


def analyze(log: list[tuple[int, Event]], spoilers: bool) -> dict[str, Any]:
    events = [e for _, e in log]
    start = next((e for e in events if e.type == "match_started"), None)
    if start is not None:
        players = list(start.data["players"])
        settings = start.data.get("settings", {}) or {}
        meta = {
            "version": start.data.get("version"),
            "prompt_version": start.data.get("prompt_version"),
            "seed": start.data.get("seed"),  # not in the spoiler-free start
            "settings": settings,
        }
        stack = settings.get("starting_stack", DEFAULTS["starting_stack"])
    else:  # a part of a log: the first hand names who plays
        first = next((e for e in events if e.type == "hand_started"), None)
        players = list(first.data["players"]) if first else []
        meta, stack = {}, DEFAULTS["starting_stack"]

    decisions = _Decisions()
    moves: list[dict[str, Any]] = []
    hands: list[dict[str, Any]] = []
    chips: dict[PlayerId, list[int]] = {p: [stack] for p in players}
    now: dict[str, Any] | None = None  # the hand being read
    street_high = 0

    for seq, event in log:
        data = event.data
        if event.source is EventSource.ENGINE:
            decisions.note(event)
            continue
        match event.type:
            case "hand_started":
                now = {
                    "hand": data["hand"],
                    "button": data["button"],
                    "players": list(data["players"]),
                    "big_blind": data["big_blind"],
                    "board": [],
                    "streets": ["preflop"],
                    "invested": dict.fromkeys(data["players"], 0),
                    "won": dict.fromkeys(data["players"], 0),
                    "aggressive": [],
                    "vpip": [],
                    "shown": [],
                    "showdown": False,
                }
                street_high = data["big_blind"]
            case "blind_posted" if now:
                now["invested"][data["player"]] += data["amount"]
            case "street_started" if now:
                now["board"] += data["cards"]
                if data["street"] not in now["streets"]:
                    now["streets"].append(data["street"])
                street_high = now["big_blind"] if data["street"] == "preflop" else 0
            case "bet_action" if now:
                player, kind, to = data["player"], data["kind"], data["to"]
                now["invested"][player] += data["added"]
                aggressive = kind == "raise" or (kind == "all_in" and to > street_high)
                street_high = (
                    max(street_high, to) if kind in ("raise", "all_in", "call") else street_high
                )
                if aggressive and player not in now["aggressive"]:
                    now["aggressive"].append(player)
                preflop_chips = data["street"] == "preflop" and kind in ("call", "raise", "all_in")
                if preflop_chips and player not in now["vpip"]:
                    now["vpip"].append(player)
                made = decisions.take(player)
                if not spoilers:  # the engine events are filtered out: unknown, not "none"
                    made = {**made, "fallback": None, "rejected": None}
                moves.append(
                    {
                        "seq": seq,
                        "index": len(moves),
                        "hand": now["hand"],
                        "street": data["street"],
                        "player": player,
                        "kind": kind,
                        "to": to,
                        "added": data["added"],
                        "aggressive": aggressive,
                        **made,
                    }
                )
            case "showdown" if now:
                now["showdown"] = True
                now["shown"] = [
                    {"player": h["player"], "cards": h["cards"], "hand": h.get("hand")}
                    for h in data["hands"]
                ]
            case "pot_awarded" if now:
                for player, amount in data["shares"].items():
                    now["won"][player] += amount
            case "hand_ended" if now:
                hands.append(_hand_out(now))
                for player in players:
                    last = chips[player][-1]
                    chips[player].append(
                        last + now["won"].get(player, 0) - now["invested"].get(player, 0)
                    )
                now = None

    hole_stats = _hole_stats(events) if spoilers else {}
    totals = {p: _totals(p, moves, hands, chips[p], hole_stats.get(p), spoilers) for p in players}
    return {
        "meta": meta,
        "players": players,
        "hands": hands,
        "chips": chips,
        "moves": moves,
        "totals": totals,
    }


def _hand_out(hand: dict[str, Any]) -> dict[str, Any]:
    pot = sum(hand["won"].values())
    return {
        "hand": hand["hand"],
        "button": hand["button"],
        "players": hand["players"],
        "big_blind": hand["big_blind"],
        "board": hand["board"],
        "streets": hand["streets"],
        "pot": pot,
        "winners": {p: amount for p, amount in hand["won"].items() if amount},
        "net": {p: hand["won"][p] - hand["invested"][p] for p in hand["players"]},
        "showdown": hand["showdown"],
        "shown": hand["shown"],  # public once the showdown happens
        "aggressive": hand["aggressive"],
        "vpip": hand["vpip"],
    }


def _hole_stats(events: list[Event]) -> dict[PlayerId, Any]:
    """The statistics that read hole cards, from the whole log (spoilers only)."""
    try:
        return stats.match_stats(events)
    except ValueError:  # a part of a log without its start
        return {}


def _totals(
    player: PlayerId,
    moves: list[dict[str, Any]],
    hands: list[dict[str, Any]],
    series: list[int],
    hole: Any,
    known: bool,
) -> dict[str, Any]:
    """`known`: the engine events are in the log (spoilers), so refusals and bot moves are known."""
    mine = [m for m in moves if m["player"] == player]
    dealt = [h for h in hands if player in h["players"]]
    count = {kind: sum(1 for m in mine if m["kind"] == kind) for kind in KINDS}
    aggressive = sum(1 for m in mine if m["aggressive"])
    calls = count["call"] + sum(1 for m in mine if m["kind"] == "all_in" and not m["aggressive"])
    shown = [h for h in dealt if h["showdown"] and any(s["player"] == player for s in h["shown"])]
    aggressive_hands = [h for h in dealt if player in h["aggressive"]]
    won_showdown = [h for h in shown if h["winners"].get(player)]
    latencies = [m["latency_ms"] for m in mine if m.get("latency_ms") is not None]
    tokens = [
        m["tokens_in"] + (m["tokens_out"] or 0) for m in mine if m.get("tokens_in") is not None
    ]
    return {
        "hands": len(dealt),
        "hands_won": sum(1 for h in dealt if h["winners"].get(player)),
        "net_chips": series[-1] - series[0],
        "final_chips": series[-1],
        "moves": len(mine),
        **{f"{kind}s": count[kind] for kind in ("fold", "check", "call", "raise")},
        "all_ins": count["all_in"],
        "fold_rate": rate(count["fold"], len(mine)),
        "call_rate": rate(count["call"], len(mine)),
        "raise_rate": rate(count["raise"], len(mine)),
        "all_in_rate": rate(count["all_in"], len(mine)),
        "vpip": rate(sum(1 for h in dealt if player in h["vpip"]), len(dealt)),
        "aggressive_actions": aggressive,
        "aggression_factor": None if not calls else aggressive / calls,
        "showdowns": len(shown),
        "showdowns_won": len(won_showdown),
        # an aggressive hand that lost the showdown / won it: from the shown cards, public
        "showdown_bluffs": sum(1 for h in aggressive_hands if h in shown and h not in won_showdown),
        "showdown_value_bets": sum(1 for h in aggressive_hands if h in won_showdown),
        # these two read the hole cards of hands nobody showed: spoilers only
        "bluff_hands": None if hole is None else hole.bluff_hands,
        "bluff_rate": None if hole is None else rate(hole.bluff_hands, hole.aggressive_hands),
        "worst_decisions": None if hole is None else hole.worst_decisions,
        # null without spoilers: the events that tell are spectators only, so unknown, not zero
        "fallbacks": None if not known else sum(1 for m in mine if m.get("fallback")),
        "refused": None if not known else sum(m.get("rejected") or 0 for m in mine),
        "response_ms_mean": sum(latencies) / len(latencies) if latencies else None,
        "tokens": sum(tokens) if tokens else None,
        **{
            f"{field}_total": _sum(mine, field)
            for field in DECISION_FIELDS
            if field != "latency_ms"
        },
    }


def _sum(moves: list[dict[str, Any]], field: str) -> int | None:
    values = [m[field] for m in moves if m.get(field) is not None]
    return sum(values) if values else None
