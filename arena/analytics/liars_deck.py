"""Liar's Deck analytics: every play, every call and every pull, and what they add up to.

With spoilers the hidden events (`hand_dealt`, `cards_hidden`, `revolver_loaded`)
say what each player held and really played. Without them a play's truth is known
only when its cards were turned over, and the numbers that need the hidden cards
are null. Moves the engine played for a model (fallbacks) are flagged and left
out of every skill number. See docs/METRICS.md for the definitions.
"""

from typing import Any

from arena.engine.types import Event, EventSource, PlayerId
from games.liars_deck.plugin import JOKER, card_rank
from games.liars_deck.variants import load_variants

# Fields the runner may put on the decision event of a move.
DECISION_FIELDS = ("latency_ms", "tokens_in", "tokens_out", "reasoning_tokens", "retries")


def rate(part: int, whole: int) -> dict[str, Any]:
    """A rate with its n: {"value": part / whole or null, "n": part, "of": whole}."""
    return {"value": None if whole == 0 else part / whole, "n": part, "of": whole}


def _counts_as_table(card: str, table_card: str | None) -> bool:
    return card_rank(card) in (table_card, JOKER)


class _Decisions:
    """What the engine logged about each player's turn before the game event of it."""

    def __init__(self) -> None:
        self._open: dict[PlayerId, dict[str, Any]] = {}

    def note(self, event: Event) -> None:
        player = event.data.get("player")
        if player is None:
            return
        made = self._open.setdefault(player, {"calls": 0, "rejected": 0})
        if event.type in ("action_accepted", "action_fallback"):
            made["calls"] += 1
            made["fallback"] = event.type == "action_fallback"
            for field in DECISION_FIELDS:
                value = event.data.get(field)
                if value is not None:  # a move of several calls adds them up
                    made[field] = made.get(field, 0) + value
        elif event.type == "action_rejected":
            made["rejected"] += 1

    def take(self, player: PlayerId) -> dict[str, Any]:
        made = self._open.pop(player, {"calls": 0, "rejected": 0})
        return {
            "fallback": bool(made.get("fallback")),
            "rejected": made["rejected"],
            **{field: made.get(field) for field in DECISION_FIELDS},
        }


def analyze(log: list[tuple[int, Event]], spoilers: bool) -> dict[str, Any]:
    events = [e for _, e in log]
    start = next((e for e in events if e.type == "match_started"), None)
    if start is not None:
        players = list(start.data["players"])
        variant = start.data.get("settings", {}).get("variant", "base")
        meta = {
            "version": start.data.get("version"),
            "prompt_version": start.data.get("prompt_version"),
            "seed": start.data.get("seed"),
            "settings": start.data.get("settings", {}),
        }
    else:  # spoiler-free: the start (seed included) is hidden; the first round names who plays
        first = next((e for e in events if e.type == "round_started"), None)
        players = list(first.data["players"]) if first else []
        variant = "base"
        meta = {"version": None, "prompt_version": None, "seed": None, "settings": {}}
    chambers = load_variants()[variant].revolver.chambers

    moves: list[dict[str, Any]] = []
    pulls: list[dict[str, Any]] = []
    rounds: list[dict[str, Any]] = []
    decisions = _Decisions()
    hands: dict[PlayerId, list[str]] = {}  # spoilers: the cards each player holds
    hand_size: dict[PlayerId, int] = {}
    live_chambers: dict[PlayerId, int] = {}
    pulled: dict[PlayerId, int] = dict.fromkeys(players, 0)
    table_card: str | None = None
    round_no = 0
    on_table: dict[str, Any] | None = None  # the last play, not yet called
    call: dict[str, Any] | None = None

    def risk(player: PlayerId) -> float | None:
        left = chambers - pulled.get(player, 0)
        if not spoilers or player not in live_chambers or left <= 0:
            return None
        return live_chambers[player] / left

    def facing() -> bool | None:
        """Whether the play on the table is a lie; null while that is not known."""
        if on_table is None or on_table["honest"] is None:
            return None
        return not on_table["honest"]

    for seq, event in log:
        data = event.data
        if event.source is EventSource.ENGINE:
            decisions.note(event)
            continue
        match event.type:
            case "revolver_loaded":
                live_chambers[data["player"]] = len(data["live"])
            case "round_started":
                round_no, table_card = data["round"], data["table_card"]
                on_table = None
                for player in data["players"]:
                    hand_size[player] = data["hand_size"]
                rounds.append(
                    {"round": round_no, "table_card": table_card, "players": list(data["players"])}
                )
            case "hand_dealt":  # spoilers only
                hands[data["player"]] = list(data["cards"])
            case "cards_played":
                player = data["player"]
                held = hands.get(player) if spoilers else None
                could_call = on_table is not None and on_table["player"] != player
                move = {
                    "seq": seq,
                    "round": round_no,
                    "player": player,
                    "kind": "play",
                    "cards": data["count"],
                    "hand_before": hand_size.get(player),
                    "cards_left": hand_size.get(player, 0) - data["count"],
                    "table_cards_held": None
                    if held is None
                    else sum(1 for c in held if _counts_as_table(c, table_card)),
                    "honest": None,
                    "false_cards": None,
                    "lie_size": None,
                    "forced": None,
                    "called": False,
                    "could_call": could_call,
                    "facing_lie": facing() if could_call else None,
                    "risk": risk(player),
                    **decisions.take(player),
                }
                hand_size[player] = move["cards_left"]
                moves.append(move)
                on_table = move
            case "cards_hidden":  # spoilers only: what the play really was
                if on_table is not None and on_table["player"] == data["player"]:
                    false = sum(1 for c in data["cards"] if not _counts_as_table(c, table_card))
                    on_table["false_cards"] = false
                    on_table["lie_size"] = false / len(data["cards"]) if data["cards"] else None
                    on_table["honest"] = false == 0
                    if not on_table["honest"]:
                        on_table["forced"] = on_table["table_cards_held"] == 0
                held = hands.get(data["player"])
                if held is not None:
                    for card in data["cards"]:
                        if card in held:
                            held.remove(card)
            case "liar_called":
                caller = data["caller"]
                made: dict[str, Any] = {
                    "fallback": False,
                    "rejected": 0,
                    **dict.fromkeys(DECISION_FIELDS),
                }
                if not data["automatic"]:
                    made = decisions.take(caller)
                call = {
                    "seq": seq,
                    "round": round_no,
                    "player": caller,
                    "kind": "call",
                    "target": data["target"],
                    "automatic": data["automatic"],
                    "correct": None,
                    "facing_lie": facing(),
                    "risk": risk(caller),
                    **made,
                }
                moves.append(call)
            case "cards_revealed":
                if on_table is not None and on_table["player"] == data["player"]:
                    on_table["honest"] = data["honest"]
                    on_table["called"] = True
                if call is not None:
                    call["correct"] = not data["honest"]
                    if call["facing_lie"] is None:
                        call["facing_lie"] = not data["honest"]
                    call = None
                on_table = None
            case "trigger_pulled":
                player = data["player"]
                pulls.append(
                    {
                        "seq": seq,
                        "round": round_no,
                        "player": player,
                        "pull": data["pull"],
                        "live": data["live"],
                        "risk": risk(player),
                    }
                )
                pulled[player] = pulled.get(player, 0) + 1
            case "round_ended":
                on_table = None

    for index, move in enumerate(moves):
        move["index"] = index
    return {
        "meta": meta,
        "players": players,
        "moves": moves,
        "pulls": pulls,
        "rounds": rounds,
        "totals": {player: _totals(player, moves, pulls, spoilers) for player in players},
        "by_round": _by_round(players, moves, rounds),
    }


def _totals(
    player: PlayerId, moves: list[dict[str, Any]], pulls: list[dict[str, Any]], spoilers: bool
) -> dict[str, Any]:
    mine = [
        m for m in moves if m["player"] == player and not (m["kind"] == "call" and m["automatic"])
    ]
    own = [m for m in mine if not m["fallback"]]  # skill numbers: the model's own moves only
    plays = [m for m in own if m["kind"] == "play"]
    known = [m for m in plays if m["honest"] is not None]
    lies = [m for m in known if not m["honest"]]
    could_play_honestly = [m for m in plays if m["table_cards_held"]]
    chosen = [m for m in lies if m["forced"] is False]
    calls = [m for m in own if m["kind"] == "call"]
    judged = [m for m in calls if m["correct"] is not None]
    # A decision with a play to call: the player called it, or played on instead.
    chances = [m for m in own if m["kind"] == "call" or (m["kind"] == "play" and m["could_call"])]
    on_lies = [m for m in chances if m["facing_lie"] is True]
    on_honest = [m for m in chances if m["facing_lie"] is False]
    times = [m["latency_ms"] for m in mine if m["latency_ms"] is not None]
    own_pulls = [p for p in pulls if p["player"] == player]
    fallbacks = sum(1 for m in mine if m["fallback"])
    sizes = [m["lie_size"] for m in lies if m["lie_size"] is not None]

    def secret(value: Any) -> Any:
        """A number that needs the hidden cards: null without spoilers."""
        return value if spoilers else None

    return {
        "plays": len(plays),
        "plays_known": len(known),
        "honest": len(known) - len(lies),
        "lies": len(lies),
        "lies_called": sum(1 for m in lies if m["called"]),
        "lie_rate": secret(rate(len(lies), len(known))),
        "chosen_lie_rate": secret(rate(len(chosen), len(could_play_honestly))),
        "forced_lies": secret(sum(1 for m in lies if m["forced"])),
        "mean_lie_size": secret(sum(sizes) / len(sizes) if sizes else None),
        "calls": len(calls),
        "calls_correct": sum(1 for m in judged if m["correct"]),
        "calls_wrong": sum(1 for m in judged if not m["correct"]),
        "call_accuracy": rate(sum(1 for m in judged if m["correct"]), len(judged)),
        "call_rate": rate(len(calls), len(chances)),
        "hit_rate": secret(rate(sum(1 for m in on_lies if m["kind"] == "call"), len(on_lies))),
        "false_alarm_rate": secret(
            rate(sum(1 for m in on_honest if m["kind"] == "call"), len(on_honest))
        ),
        "cards_claimed": sum(m["cards"] for m in plays),
        "pulls": len(own_pulls),
        "pulls_survived": sum(1 for p in own_pulls if not p["live"]),
        "fallbacks": fallbacks,
        "fallback_share": rate(fallbacks, len(mine)),
        "rejected_per_move": None if not mine else sum(m["rejected"] for m in mine) / len(mine),
        "response_ms_total": sum(times) if times else None,
        "response_ms_mean": sum(times) / len(times) if times else None,
        "tokens_in": _sum(mine, "tokens_in"),
        "tokens_out": _sum(mine, "tokens_out"),
        "reasoning_tokens": _sum(mine, "reasoning_tokens"),
    }


def _sum(moves: list[dict[str, Any]], field: str) -> int | None:
    values = [m[field] for m in moves if m[field] is not None]
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
                "fallbacks": sum(1 for m in mine if m["fallback"]),
            }
        out.append({"round": r["round"], "players": cell})
    return out
