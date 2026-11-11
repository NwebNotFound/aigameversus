"""Liar's Deck analytics: every play, every call and every pull, and what they add up to.

With spoilers the hidden `cards_hidden` events say whether each play was a lie.
Without them a play's honesty is known only when its cards were turned over, so
`honest` is null for plays nobody called. See docs/METRICS.md for the definitions.
"""

from typing import Any

from arena.engine.types import Event, EventSource, PlayerId
from games.liars_deck.plugin import JOKER, card_rank
from games.liars_deck.variants import load_variants

# Fields the runner may put on the decision event of a move (Builder's event fields).
DECISION_FIELDS = ("latency_ms", "tokens_in", "tokens_out", "reasoning_tokens", "retries")


def _ratio(part: int, whole: int) -> float | None:
    return None if whole == 0 else part / whole


def analyze(log: list[tuple[int, Event]], spoilers: bool) -> dict[str, Any]:
    events = [e for _, e in log]
    start = next((e for e in events if e.type == "match_started"), None)
    players: list[PlayerId] = []
    variant = "base"
    if start is not None:
        players = list(start.data["players"])
        variant = start.data.get("settings", {}).get("variant", "base")
    else:  # spoiler-free: the first round names who plays
        first = next((e for e in events if e.type == "round_started"), None)
        players = list(first.data["players"]) if first else []

    moves: list[dict[str, Any]] = []
    rounds: list[dict[str, Any]] = []
    pulls: list[dict[str, Any]] = []
    live_chambers: dict[PlayerId, int] = {}
    pulled: dict[PlayerId, int] = dict.fromkeys(players, 0)
    chambers = load_variants()[variant].revolver.chambers
    table_card = None
    round_no = 0
    decision: dict[PlayerId, dict[str, Any]] = {}  # the last decision of each player
    play_of: dict[PlayerId, dict[str, Any]] = {}  # the open (uncalled) play of each player
    call: dict[str, Any] | None = None
    hand_size: dict[PlayerId, int] = {}

    for seq, event in log:
        data = event.data
        if event.source is EventSource.ENGINE:
            if event.type in ("action_accepted", "action_fallback") and "player" in data:
                decision[data["player"]] = {
                    "fallback": event.type == "action_fallback",
                    **{field: data.get(field) for field in DECISION_FIELDS},
                }
            if event.type == "agent_failed" and "player" in data:
                decision.setdefault(data["player"], {})["failed"] = True
            continue
        match event.type:
            case "revolver_loaded":
                live_chambers[data["player"]] = len(data["live"])
            case "round_started":
                round_no, table_card = data["round"], data["table_card"]
                for player in data["players"]:
                    hand_size[player] = data["hand_size"]
                rounds.append(
                    {"round": round_no, "table_card": table_card, "players": list(data["players"])}
                )
            case "cards_played":
                player = data["player"]
                hand_size[player] = hand_size.get(player, 0) - data["count"]
                made = decision.pop(player, {})
                move = {
                    "seq": seq,
                    "round": round_no,
                    "player": player,
                    "kind": "play",
                    "cards": data["count"],
                    "cards_left": hand_size[player],
                    "honest": None,
                    "called": False,
                    "fallback": bool(made.get("fallback")),
                    **{field: made.get(field) for field in DECISION_FIELDS},
                }
                moves.append(move)
                play_of[player] = move
            case "cards_hidden":  # spoilers only: what the play really was
                move = play_of.get(data["player"])
                if move is not None:
                    move["honest"] = all(
                        card_rank(card) in (table_card, JOKER) for card in data["cards"]
                    )
            case "liar_called":
                made = {} if data["automatic"] else decision.pop(data["caller"], {})
                call = {
                    "seq": seq,
                    "round": round_no,
                    "player": data["caller"],
                    "kind": "call",
                    "target": data["target"],
                    "automatic": data["automatic"],
                    "correct": None,
                    "fallback": bool(made.get("fallback")),
                    **{field: made.get(field) for field in DECISION_FIELDS},
                }
                moves.append(call)
            case "cards_revealed":
                played = play_of.pop(data["player"], None)
                if played is not None:
                    played["honest"] = data["honest"]
                    played["called"] = True
                if call is not None:
                    call["correct"] = not data["honest"]
                    call = None
            case "trigger_pulled":
                player = data["player"]
                left = chambers - pulled.get(player, 0)
                risk = None
                if spoilers and player in live_chambers and left > 0:
                    risk = live_chambers[player] / left
                pulled[player] = pulled.get(player, 0) + 1
                pulls.append(
                    {
                        "seq": seq,
                        "round": round_no,
                        "player": player,
                        "pull": data["pull"],
                        "live": data["live"],
                        "risk": risk,
                    }
                )
            case "round_ended":
                play_of.clear()

    for index, move in enumerate(moves):
        move["index"] = index
    return {
        "players": players,
        "moves": moves,
        "pulls": pulls,
        "rounds": rounds,
        "totals": {player: _totals(player, moves, pulls) for player in players},
        "by_round": _by_round(players, moves, rounds),
    }


def _totals(player: PlayerId, moves: list[dict[str, Any]], pulls: list[dict[str, Any]]) -> dict:
    plays = [m for m in moves if m["player"] == player and m["kind"] == "play"]
    known = [m for m in plays if m["honest"] is not None]
    lies = [m for m in known if not m["honest"]]
    calls = [
        m for m in moves if m["player"] == player and m["kind"] == "call" and not m["automatic"]
    ]
    judged = [m for m in calls if m["correct"] is not None]
    times = [
        m["latency_ms"] for m in moves if m["player"] == player and m["latency_ms"] is not None
    ]
    own_pulls = [p for p in pulls if p["player"] == player]
    return {
        "plays": len(plays),
        "plays_known": len(known),
        "honest": len(known) - len(lies),
        "lies": len(lies),
        "lies_called": sum(1 for m in lies if m["called"]),
        "lie_rate": _ratio(len(lies), len(known)),
        "calls": len(calls),
        "calls_correct": sum(1 for m in judged if m["correct"]),
        "calls_wrong": sum(1 for m in judged if not m["correct"]),
        "call_accuracy": _ratio(sum(1 for m in judged if m["correct"]), len(judged)),
        "cards_claimed": sum(m["cards"] for m in plays),
        "pulls": len(own_pulls),
        "pulls_survived": sum(1 for p in own_pulls if not p["live"]),
        "fallbacks": sum(1 for m in moves if m["player"] == player and m["fallback"]),
        "thinking_ms_total": sum(times) if times else None,
        "thinking_ms_mean": sum(times) / len(times) if times else None,
        "tokens_in": _sum(moves, player, "tokens_in"),
        "tokens_out": _sum(moves, player, "tokens_out"),
    }


def _sum(moves: list[dict[str, Any]], player: PlayerId, field: str) -> int | None:
    values = [m[field] for m in moves if m["player"] == player and m[field] is not None]
    return sum(values) if values else None


def _by_round(players: list[PlayerId], moves: list[dict[str, Any]], rounds: list[dict]) -> list:
    """Per round and player: honest plays, lies, unknown plays and calls (for the heatmap)."""
    out = []
    for r in rounds:
        cell = {}
        for player in players:
            mine = [m for m in moves if m["round"] == r["round"] and m["player"] == player]
            plays = [m for m in mine if m["kind"] == "play"]
            cell[player] = {
                "honest": sum(1 for m in plays if m["honest"] is True),
                "lies": sum(1 for m in plays if m["honest"] is False),
                "unknown": sum(1 for m in plays if m["honest"] is None),
                "calls": sum(1 for m in mine if m["kind"] == "call" and not m["automatic"]),
            }
        out.append({"round": r["round"], "players": cell})
    return out
