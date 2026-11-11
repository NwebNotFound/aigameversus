# ruff: noqa: E501  (lines of prose)
"""The match report for the stats screen: at a glance, a ranking table, key moments.

Everything is computed here so the web does no maths: `at_a_glance` (winners,
length, moves, errors, speed, tokens, the turning point), `ranking` (one row per
player in rank order, with `columns` describing each field so a table can be
drawn generically) and `key_moments` (seq, importance 1-3, a sentence in en and
de). The API adds cost and duration from the match record and the ledger.

Built from the same spoiler-filtered log and analytics as the rest: what needs
hidden cards or private events (lies, refused answers, fallbacks, roles before
death) is null without spoilers.
"""

from collections import Counter
from collections.abc import Callable, Mapping
from typing import Any

from arena.analytics import situation as sit
from arena.chronicle.text import CAUSES
from arena.engine.types import Event
from games.werewolf.selection import load_roles

Log = list[tuple[int, Event]]


def report(
    game: str, log: Log, spoilers: bool, numbers: dict[str, Any], names: Mapping[str, str]
) -> dict[str, Any]:
    name = lambda seat: names.get(seat, seat)  # noqa: E731
    start = next((e for _, e in log if e.type == "match_started"), None)
    players = list(start.data.get("players", [])) if start else []
    finished = next((e for _, e in log if e.type == "match_finished"), None)
    ranks = {p["player"]: p["rank"] for p in finished.data["placements"]} if finished else {}
    engine = _engine_counts(log, players, spoilers)
    build = GAMES.get(game)
    rows, columns, moments, length = (
        build(log, spoilers, numbers, players, name) if build else ([], [], [], {})
    )
    columns = [*columns, *ENGINE_COLUMNS]
    for column in columns:
        column["better"] = BETTER.get(column["key"])
    ranking = []
    for row in rows:
        row.update(engine["per_player"][row["player"]])
        ranking.append(
            {
                "seat": row["player"],
                "rank": ranks.get(row["player"]),
                "values": [cell(column, row[column["key"]]) for column in columns],
            }
        )
    ranking.sort(key=lambda r: (r["rank"] is None, r["rank"] or 0, players.index(r["seat"])))
    moments.sort(key=lambda m: m["seq"])
    turning = max(
        moments, key=lambda m: (m.get("turning", False), m["importance"], -m["seq"]), default=None
    )
    return {
        "at_a_glance": {
            "over": finished is not None,
            "winners": sorted((p for p, r in ranks.items() if r == 1), key=players.index),
            "players": len(players),
            "length": {"unit": unit, "count": count}
            if (unit := next(iter(length), None)) and (count := length[unit]) is not None
            else None,
            **engine["totals"],
            "tool_errors": engine["totals"]["refused"],
            "turning_point": (
                {k: turning[k] for k in ("seq", "kind", "players", "text")}
                if turning and turning.get("turning")
                else None
            ),
        },
        "columns": columns,
        "ranking": ranking,
        "key_moments": moments,
    }


def _label(en: str, de: str) -> dict[str, str]:
    return {"en": en, "de": de}


# Which way a value is better, for bars and sorting; None: neither (a style, not a score).
BETTER = {
    "call_accuracy": "higher",
    "chips": "higher",
    "pots_won": "higher",
    "biggest_pot": "higher",
    "out_in_hand": "higher",
    "survived": "higher",
    "vote_accuracy": "higher",
    "refused": "lower",
    "fallbacks": "lower",
    "response_ms_mean": "lower",
    "tokens": "lower",
    "cost_micro_eur": "lower",
}


def cell(column: dict[str, Any], raw: Any) -> dict[str, Any]:
    """One value of a ranking row with what a table needs to draw it: a rate keeps its n."""
    out = {k: column[k] for k in ("key", "label", "kind", "better")}
    for flag in ("spoilers", "heuristic"):
        if column.get(flag):
            out[flag] = True
    if isinstance(raw, dict) and "value" in raw:
        out.update(value=raw["value"], n=raw["n"], of=raw["of"])
    else:
        out["value"] = raw
    return out


ENGINE_COLUMNS = [
    {"key": "moves", "label": _label("Moves", "Züge"), "kind": "number", "spoilers": True},
    {
        "key": "refused",
        "label": _label("Refused answers", "Abgelehnte Antworten"),
        "kind": "number",
        "spoilers": True,
    },
    {
        "key": "fallbacks",
        "label": _label("Bot moves", "Bot-Züge"),
        "kind": "number",
        "spoilers": True,
    },
    {
        "key": "response_ms_mean",
        "label": _label("Response time (mean, ms)", "Antwortzeit (Mittel, ms)"),
        "kind": "number",
    },
    {"key": "tokens", "label": _label("Tokens", "Tokens"), "kind": "number"},
]


def _engine_counts(log: Log, players: list[str], spoilers: bool) -> dict[str, Any]:
    """Moves, refused answers and bot moves per player (private events: spoilers only), and
    response time and tokens from the per-move `decision` events once the log has them."""
    count: dict[str, Counter] = {p: Counter() for p in players}
    times: dict[str, list[int]] = {p: [] for p in players}
    tokens: dict[str, int] = {p: 0 for p in players}
    for _, event in log:
        player = event.data.get("player")
        if player not in count:
            continue
        if event.type in ("action_accepted", "action_fallback"):
            count[player]["moves"] += 1
        if event.type == "action_rejected":
            count[player]["refused"] += 1
        if event.type == "action_fallback":
            count[player]["fallbacks"] += 1
        if event.type == "decision":
            if event.data.get("latency_ms") is not None:
                times[player].append(event.data["latency_ms"])
            tokens[player] += (event.data.get("tokens_in") or 0) + (
                event.data.get("tokens_out") or 0
            )
    per_player = {}
    for p in players:
        private = {k: count[p][k] if spoilers else None for k in ("moves", "refused", "fallbacks")}
        per_player[p] = {
            **private,
            "response_ms_mean": round(sum(times[p]) / len(times[p])) if times[p] else None,
            "tokens": tokens[p] or None,
        }
    all_times = [t for p in players for t in times[p]]
    totals = {
        "moves": sum(c["moves"] for c in count.values()) if spoilers else None,
        "refused": sum(c["refused"] for c in count.values()) if spoilers else None,
        "fallbacks": sum(c["fallbacks"] for c in count.values()) if spoilers else None,
        "response_ms_mean": round(sum(all_times) / len(all_times)) if all_times else None,
        "tokens": sum(tokens.values()) or None,
    }
    return {"per_player": per_player, "totals": totals}


def _moment(
    seq: int,
    kind: str,
    players: list[str],
    importance: int,
    en: str,
    de: str,
    turning: bool = False,
) -> dict[str, Any]:
    out = {
        "seq": seq,
        "kind": kind,
        "players": list(players),
        "importance": importance,
        "text": _label(en, de),
    }
    if turning:
        out["turning"] = True
    return out


# --- Liar's Deck --------------------------------------------------------------


def _liars(log: Log, spoilers: bool, numbers: dict, players: list[str], name: Callable[[str], str]):
    totals = numbers["totals"]
    rows = [
        {
            "player": p,
            "plays": totals[p]["plays"],
            "lies": totals[p]["lies"] if spoilers else None,
            "lie_rate": totals[p]["lie_rate"],  # a rate with its n; null without spoilers
            "calls": totals[p]["calls"],
            "call_accuracy": totals[p]["call_accuracy"],
            "pulls": totals[p]["pulls"],
            "max_risk": max(
                (pull["risk"] for pull in numbers["pulls"] if pull["player"] == p), default=None
            ),
        }
        for p in players
    ]
    columns = [
        {"key": "plays", "label": _label("Plays", "Züge"), "kind": "number"},
        {"key": "lies", "label": _label("Lies", "Lügen"), "kind": "number", "spoilers": True},
        {
            "key": "lie_rate",
            "label": _label("Lie rate", "Lügenquote"),
            "kind": "rate",
            "spoilers": True,
        },
        {"key": "calls", "label": _label("Liar calls", "Lügner-Rufe"), "kind": "number"},
        {"key": "call_accuracy", "label": _label("Calls right", "Rufe richtig"), "kind": "rate"},
        {"key": "pulls", "label": _label("Trigger pulls", "Abzüge"), "kind": "number"},
        {
            "key": "max_risk",
            "label": _label("Highest risk taken", "Höchstes Risiko"),
            "kind": "rate",
        },
    ]
    moments: list[dict] = []
    alive = len(players)
    call = None
    for seq, event in log:
        data = event.data
        if event.type == "liar_called" and not data["automatic"]:
            call = data
        elif event.type == "cards_revealed" and call:
            caller, target = name(call["caller"]), name(call["target"])
            if data["honest"]:
                moments.append(
                    _moment(
                        seq,
                        "wrong_call",
                        [call["caller"], call["target"]],
                        2,
                        f"{caller} called {target} a liar, but {target} told the truth.",
                        f"{caller} nannte {target} einen Lügner, aber {target} sagte die Wahrheit.",
                    )
                )
            else:
                moments.append(
                    _moment(
                        seq,
                        "caught",
                        [call["caller"], call["target"]],
                        2,
                        f"{caller} caught {target} lying.",
                        f"{caller} erwischte {target} beim Lügen.",
                    )
                )
            call = None
        elif event.type == "players_eliminated":
            alive -= len(data["players"])
            for p in data["players"]:
                final = alive == 1
                moments.append(
                    _moment(
                        seq,
                        "eliminated",
                        [p],
                        3,
                        f"{name(p)} is out{' and the match is decided' if final else ''}.",
                        f"{name(p)} ist raus{' und die Partie entschieden' if final else ''}.",
                        turning=final,
                    )
                )
        elif event.type == "match_over" and data.get("winner"):
            moments.append(
                _moment(
                    seq,
                    "winner",
                    [data["winner"]],
                    3,
                    f"{name(data['winner'])} wins.",
                    f"{name(data['winner'])} gewinnt.",
                )
            )
    rounds = max((r["round"] for r in numbers.get("rounds", [])), default=0)
    return rows, columns, moments, {"rounds": rounds}


# --- Poker --------------------------------------------------------------------


def _poker(log: Log, spoilers: bool, numbers: dict, players: list[str], name: Callable[[str], str]):
    facts = sit._poker_facts(log, spoilers)
    won: Counter[str] = Counter()
    biggest: dict[str, int] = {}
    pots: list[tuple[int, int, list[str]]] = []
    eliminated_in: dict[str, int] = {}
    hand = 0
    moments: list[dict] = []
    for seq, event in log:
        data = event.data
        if event.type == "hand_started":
            hand = data["hand"]
        elif event.type == "pot_awarded":
            for p, share in data["shares"].items():
                won[p] += 1
                biggest[p] = max(biggest.get(p, 0), share)
            pots.append((data["amount"], seq, sorted(data["shares"])))
        elif event.type == "players_eliminated":
            for p in data["players"]:
                eliminated_in[p] = hand
                moments.append(
                    _moment(
                        seq,
                        "eliminated",
                        [p],
                        3,
                        f"{name(p)} is out in hand {hand}.",
                        f"{name(p)} scheidet in Hand {hand} aus.",
                    )
                )
    top = sorted(pots, reverse=True)[:3]
    for rank, (amount, seq, to) in enumerate(top):
        who = ", ".join(name(p) for p in to)
        moments.append(
            _moment(
                seq,
                "big_pot",
                to,
                2,
                f"{who} wins a pot of {amount:,}.",
                f"{who} gewinnt einen Pot von {amount:,}.".replace(",", "."),
                turning=rank == 0,
            )
        )
    rows = [
        {
            "player": p,
            "chips": facts["stacks"].get(p, 0),
            "pots_won": won[p],
            "biggest_pot": biggest.get(p),
            "out_in_hand": eliminated_in.get(p),
        }
        for p in players
    ]
    columns = [
        {"key": "chips", "label": _label("Chips", "Chips"), "kind": "number"},
        {"key": "pots_won", "label": _label("Pots won", "Pots gewonnen"), "kind": "number"},
        {"key": "biggest_pot", "label": _label("Biggest pot", "Größter Pot"), "kind": "number"},
        {"key": "out_in_hand", "label": _label("Out in hand", "Raus in Hand"), "kind": "number"},
    ]
    return rows, columns, moments, {"hands": facts["hand"] or 0}


# --- Werewolf -----------------------------------------------------------------


def _werewolf(
    log: Log, spoilers: bool, numbers: dict, players: list[str], name: Callable[[str], str]
):
    roles = numbers["meta"]["roles"] or {}
    revealed = numbers["meta"]["revealed"]
    teams = {r.id: r.team for r in load_roles().values()}
    accused = Counter(a["target"] for a in numbers["accusations"])
    made = Counter(a["by"] for a in numbers["accusations"])
    accuracy = numbers["votes"]["accuracy"] or {}
    died: dict[str, dict] = {}
    for phase in numbers["phases"]:
        for death in phase["deaths"]:
            died[death["player"]] = {
                "phase": f"{phase['kind']} {phase['number']}",
                "cause": death["cause"],
            }
    claims: dict[str, list[str]] = {}
    for claim in numbers["claims"]:
        claims.setdefault(claim["player"], []).append(claim["role"])
    rows = [
        {
            "player": p,
            "role": roles.get(p) or revealed.get(p),
            "survived": p not in died,
            "died": died.get(p, {}).get("phase"),
            "accused_by_others": accused[p],
            "accusations_made": made[p],
            "claims": claims.get(p, []),
            "vote_accuracy": accuracy.get(p),
        }
        for p in players
    ]
    columns = [
        {"key": "role", "label": _label("Role", "Rolle"), "kind": "role"},
        {"key": "survived", "label": _label("Survived", "Überlebt"), "kind": "bool"},
        {"key": "died", "label": _label("Died", "Gestorben"), "kind": "text"},
        {
            "key": "accused_by_others",
            "label": _label("Accused by others", "Von anderen beschuldigt"),
            "kind": "number",
            "heuristic": True,
        },
        {
            "key": "accusations_made",
            "label": _label("Accusations made", "Beschuldigungen"),
            "kind": "number",
            "heuristic": True,
        },
        {
            "key": "claims",
            "label": _label("Claimed", "Behauptet"),
            "kind": "roles",
            "heuristic": True,
        },
        {
            "key": "vote_accuracy",
            "label": _label("Votes on wolves", "Stimmen gegen Wölfe"),
            "kind": "rate",
            "spoilers": True,
        },
    ]
    winner_team = None
    moments: list[dict] = []
    for _seq, event in log:
        if event.type == "game_over":
            winner_team = event.data.get("winner")
    first_wrong = True
    for phase in numbers["phases"]:
        for death in phase["deaths"]:
            p, role = death["player"], death["role"]
            cause_en = CAUSES["en"].get(death["cause"], (death["cause"] or "").replace("_", " "))
            cause_de = CAUSES["de"].get(death["cause"], (death["cause"] or "").replace("_", " "))
            role_en = f", the {role.replace('_', ' ')}," if role else ""
            role_de = f" ({load_roles()[role].name})" if role in load_roles() else ""
            executed = death["cause"] == "executed"
            wrong = (
                executed
                and role is not None
                and teams.get(role) == "village"
                and winner_team == "wolves"
            )
            turning = wrong and first_wrong
            first_wrong = first_wrong and not wrong
            moments.append(
                _moment(
                    death["seq"],
                    "execution" if executed else "death",
                    [p],
                    3 if executed else 2,
                    f"{name(p)}{role_en} was {cause_en}.",
                    f"{name(p)}{role_de} wurde {cause_de}.",
                    turning=turning,
                )
            )
    for claim in numbers["claims"]:
        if claim["disproved"]:
            moments.append(
                _moment(
                    claim["seq"],
                    "false_claim",
                    [claim["player"]],
                    3,
                    f"{name(claim['player'])} claimed to be the {claim['role'].replace('_', ' ')}, but was not.",
                    f"{name(claim['player'])} behauptete, {load_roles()[claim['role']].name} zu sein, und war es nicht.",
                )
            )
        elif claim["counterclaimed_by"]:
            moments.append(
                _moment(
                    claim["seq"],
                    "counterclaim",
                    [claim["player"], *claim["counterclaimed_by"]],
                    2,
                    f"{name(claim['player'])} claims the {claim['role'].replace('_', ' ')}, against {', '.join(name(c) for c in claim['counterclaimed_by'])}.",
                    f"{name(claim['player'])} beansprucht {load_roles()[claim['role']].name}, gegen {', '.join(name(c) for c in claim['counterclaimed_by'])}.",
                )
            )
    return (
        rows,
        columns,
        moments,
        {"days": max((p["number"] for p in numbers["phases"] if p["kind"] == "day"), default=0)},
    )


GAMES = {"liars_deck": _liars, "poker": _poker, "werewolf": _werewolf}
