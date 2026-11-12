# ruff: noqa: E501  (lines of prose)
"""Werewolf analytics: votes, role claims, accusations, a stance per event, and phase recaps.

Votes come from the game's own events and are facts. Claims and accusations are
read from what players said with simple rules, so they are marked `heuristic`:
a sentence with "I am ... the seer" claims the seer; a sentence that names a seat
next to words like "suspect" or "wolf" accuses it, one with "trust" or
"innocent" defends it, and a negation ("not", "nicht") makes it neither. A vote's
reason counts as speech about its target. The UI reads `stance` per event and
needs no language processing of its own.

Like all analytics, a spoiler-free answer reads public events only: wolf chat,
lover chat, roles and the night are for spectators.
"""

import re
from collections import Counter
from collections.abc import Mapping
from typing import Any, Protocol

from arena.analytics.liars_deck import rate
from arena.chronicle.text import CAUSES
from arena.engine.types import MESSAGE, Event
from games.werewolf.selection import load_roles

Log = list[tuple[int, Event]]

ACCUSE = re.compile(
    r"\b(suspect\w*|suspicious|sus|wolf|wolves|werewolf|lying|liar|lies|lied|scum|concerning|"
    r"eliminate|execute|lynch|vote (?:for|out)|verdächtig\w*|werwolf|werwölfe|lügt|lügner|gelogen|"
    r"rauswählen|hinrichten)\b",
    re.IGNORECASE,
)
DEFEND = re.compile(
    r"\b(trust\w*|innocent|cleared?|believe|vouch|town|confirmed|vertrau\w*|unschuldig|glaube\w*|sauber)\b",
    re.IGNORECASE,
)
NEGATION = re.compile(
    r"\b(not|no|never|don't|doesn't|isn't|nicht|kein\w*|nie)\b|n't\b", re.IGNORECASE
)
SENTENCE = re.compile(r"(?<=[.!?;\n])\s+")
SEAT = re.compile(r"\bp(\d{1,2})\b")


def _role_words() -> dict[str, str]:
    """Words for each role, English (from its id) and German (its name), lower case."""
    words = {}
    for role in load_roles().values():
        words[role.id.replace("_", " ")] = role.id
        words[role.name.lower()] = role.id
    words["wolf"] = "werewolf"
    return words


ROLE_WORDS = _role_words()
_ROLE_PATTERN = "|".join(sorted((re.escape(w) for w in ROLE_WORDS), key=len, reverse=True))
CLAIM = re.compile(
    rf"\b(?:i am|i'm|im|ich bin)\b(?P<between>[^.!?]{{0,40}}?)\b(?:the |a |an |der |die |das |ein |eine |einer )?"
    rf"(?:simple |plain |humble |normal\w* |einfache\w* )?(?P<role>{_ROLE_PATTERN})\b",
    re.IGNORECASE,
)


def _sentences(text: str) -> list[str]:
    return [part for part in SENTENCE.split(text) if part.strip()]


def _mentions(sentence: str, players: list[str], names: Mapping[str, str], me: str) -> list[str]:
    found = [f"p{n}" for n in SEAT.findall(sentence)]
    found += [
        seat
        for seat, name in names.items()
        if name and re.search(rf"(?<!\w){re.escape(name)}(?!\w)", sentence, re.IGNORECASE)
    ]
    return sorted({seat for seat in found if seat in players and seat != me}, key=players.index)


def read_speech(
    text: str, speaker: str, players: list[str], names: Mapping[str, str]
) -> dict[str, Any]:
    """What a player's words say, by rule: whom they suspect or defend, which role they claim."""
    suspects, defends, claim = [], [], None
    for sentence in _sentences(text):
        if (
            claim is None
            and (match := CLAIM.search(sentence))
            and not NEGATION.search(match.group("between"))
        ):
            claim = ROLE_WORDS[match.group("role").lower()]
        named = _mentions(sentence, players, names, speaker)
        if not named or NEGATION.search(sentence):
            continue
        if ACCUSE.search(sentence):
            suspects += [seat for seat in named if seat not in suspects]
        elif DEFEND.search(sentence):
            defends += [seat for seat in named if seat not in defends]
    return {
        "suspects": suspects,
        "defends": [s for s in defends if s not in suspects],
        "claims": claim,
    }


def analyze(log: Log, spoilers: bool, names: Mapping[str, str] | None = None) -> dict[str, Any]:
    names = names or {}
    start = next((e for _, e in log if e.type == "match_started"), None)
    players = list(start.data.get("players", [])) if start else []
    roles: dict[str, str] = {}  # spoilers: who is what; else only the roles revealed at death
    revealed: dict[str, str] = {}
    phase = {
        "kind": "setup",
        "number": 0,
        "from_seq": 0,
        "deaths": [],
        "accused": Counter(),
        "votes": None,
        "executed": None,
    }
    phases: list[dict[str, Any]] = []
    days: dict[int, dict[str, Any]] = {}
    claims: list[dict[str, Any]] = []
    accusations: list[dict[str, Any]] = []
    stance: dict[int, dict[str, Any]] = {}
    last_vote: dict[str, tuple[int, str]] = {}  # a vote's reason follows it as a message

    def enter(kind: str, number: int, seq: int) -> None:
        nonlocal phase
        phase = {
            "kind": kind,
            "number": number,
            "from_seq": seq,
            "deaths": [],
            "accused": Counter(),
            "votes": None,
            "executed": None,
        }
        phases.append(phase)

    for seq, event in log:
        data = event.data
        if event.type == "role_assigned":
            roles[data["player"]] = data["role"]
        elif event.type == "night_started":
            enter("night", data["night"], seq)
        elif event.type == "day_started":
            # The morning's deaths stay with the night that caused them.
            enter("day", data["day"], seq)
        elif event.type == "player_died":
            phase["deaths"].append(
                {
                    "seq": seq,
                    "player": data["player"],
                    "cause": data.get("cause"),
                    "role": data.get("role"),
                }
            )
            if data.get("role"):
                revealed[data["player"]] = data["role"]
        elif event.type == "vote_cast":
            day = days.setdefault(
                phase["number"],
                {"day": phase["number"], "votes": {}, "tally": {}, "executed": None},
            )
            target = data["target"]  # None: the player abstained
            day["votes"][data["player"]] = target
            cast = [t for t in day["votes"].values() if t is not None]
            day["tally"] = dict(Counter(cast).most_common())
            day["abstained"] = sorted(p for p, t in day["votes"].items() if t is None)
            last_vote[data["player"]] = (seq, target)
            stance[seq] = {
                "player": data["player"],
                "votes_for": target,
                "suspects": [] if target is None else [target],
                "defends": [],
                "claims": None,
                "heuristic": False,
            }
            if target is not None:
                accusations.append(
                    {
                        "seq": seq,
                        "day": phase["number"],
                        "by": data["player"],
                        "target": target,
                        "source": "vote",
                        "heuristic": False,
                    }
                )
        elif event.type == "vote_result":
            day = days.setdefault(
                data["day"], {"day": data["day"], "votes": {}, "tally": {}, "executed": None}
            )
            day["tally"] = dict(sorted(data["counts"].items(), key=lambda item: -item[1]))
            day["executed"] = data.get("executed")
            phase["votes"], phase["executed"] = day["tally"], day["executed"]
        elif event.type == MESSAGE:
            speaker = data["player"]
            said = read_speech(data["text"], speaker, players, names)
            reason_of = last_vote.pop(speaker, None)
            if reason_of and seq == reason_of[0] + 1:
                # The reason of the vote just cast: it belongs to the vote, not to a new accusation.
                stance[reason_of[0]]["reason_seq"] = seq
                said["suspects"] = [t for t in said["suspects"] if t != reason_of[1]]
            if said["claims"]:
                claims.append(
                    {
                        "seq": seq,
                        "player": speaker,
                        "role": said["claims"],
                        "phase": dict(kind=phase["kind"], number=phase["number"]),
                        "heuristic": True,
                    }
                )
            for target in said["suspects"]:
                accusations.append(
                    {
                        "seq": seq,
                        "day": phase["number"],
                        "by": speaker,
                        "target": target,
                        "source": "speech",
                        "heuristic": True,
                    }
                )
                phase["accused"][target] += 1
            if said["suspects"] or said["defends"] or said["claims"]:
                stance[seq] = {"player": speaker, "votes_for": None, **said, "heuristic": True}

    known = roles if spoilers else {}
    return {
        "players": players,
        "votes": _votes(days, known),
        "claims": _contradictions(claims, revealed),
        "accusations": accusations,
        "stance": stance,
        "phases": [_phase_out(p) for p in phases],
        "meta": {"roles": known or None, "revealed": revealed},
    }


def _votes(days: dict[int, dict], roles: dict[str, str]) -> dict[str, Any]:
    """Every day's votes; with spoilers how often the village side voted for a wolf."""
    out: dict[str, Any] = {"days": [days[d] for d in sorted(days)], "accuracy": None}
    if roles:
        teams = {p: load_roles()[r].team for p, r in roles.items()}
        right: Counter[str] = Counter()
        cast: Counter[str] = Counter()
        for day in days.values():
            for voter, target in day["votes"].items():
                if teams.get(voter) == "village" and target is not None:
                    cast[voter] += 1
                    right[voter] += teams.get(target) == "wolves"
        out["accuracy"] = {voter: rate(right[voter], cast[voter]) for voter in sorted(cast)}
    return out


def _contradictions(claims: list[dict], revealed: dict[str, str]) -> list[dict]:
    """Each claim with who else claimed the same unique role, and whether death disproved it."""
    unique = {role_id for role_id, role in load_roles().items() if role.unique}
    first: dict[tuple[str, str], dict] = {}
    for claim in claims:
        first.setdefault((claim["player"], claim["role"]), claim)  # a repeated claim counts once
    out = []
    for claim in first.values():
        rivals = sorted(
            {
                c["player"]
                for c in first.values()
                if c["role"] == claim["role"] and c["player"] != claim["player"]
            }
        )
        dead_as = revealed.get(claim["player"])
        earlier = [
            c["role"]
            for c in first.values()
            if c["player"] == claim["player"] and c["seq"] < claim["seq"]
        ]
        out.append(
            {
                **claim,
                "changed_from": earlier[-1] if earlier else None,  # the same player, another role
                "counterclaimed_by": rivals if claim["role"] in unique else [],
                "disproved": dead_as is not None and dead_as != claim["role"],
                "true_role": dead_as,
            }
        )
    return out


def _phase_out(phase: dict) -> dict:
    return {
        **{k: v for k, v in phase.items() if k != "accused"},
        "accused": dict(phase["accused"].most_common()),
    }


# --- recaps -------------------------------------------------------------------


class Narrator(Protocol):
    """Turns one phase into a short recap. The default is a template; a cheap model may follow."""

    def recap(self, phase: dict[str, Any], lang: str, name) -> str: ...


class TemplateNarrator:
    def recap(self, phase: dict[str, Any], lang: str, name) -> str:
        de = lang == "de"
        if phase["kind"] == "night":
            head = f"{'Nacht' if de else 'Night'} {phase['number']}: "
        else:
            head = f"{'Tag' if de else 'Day'} {phase['number']}: "
        parts = []
        if phase["accused"]:
            target, times = next(iter(phase["accused"].items()))
            parts.append(
                f"{name(target)} {'wurde' if de else 'was'} {times}× {'beschuldigt' if de else 'accused'}"
            )
        if phase["votes"]:
            tally = ", ".join(f"{name(t)} {n}" for t, n in phase["votes"].items())
            parts.append(f"{'Stimmen' if de else 'votes'}: {tally}")
        for death in phase["deaths"]:
            cause = CAUSES[lang].get(death["cause"], (death["cause"] or "").replace("_", " "))
            role = ""
            if death["role"]:
                word = load_roles()[death["role"]].name if de else death["role"].replace("_", " ")
                role = f" ({word})"
            parts.append(f"{name(death['player'])}{role} {'starb' if de else 'died'}, {cause}")
        if not parts:
            parts.append("nichts Öffentliches geschah" if de else "nothing happened in public")
        return head + "; ".join(parts) + "."


def recaps(
    analytics: dict[str, Any], names: Mapping[str, str], narrator: Narrator | None = None
) -> list[dict[str, Any]]:
    narrator = narrator or TemplateNarrator()
    name = lambda seat: names.get(seat, seat)  # noqa: E731
    return [
        {
            "kind": p["kind"],
            "number": p["number"],
            "from_seq": p["from_seq"],
            "text": {lang: narrator.recap(p, lang, name) for lang in ("en", "de")},
        }
        for p in analytics["phases"]
    ]
