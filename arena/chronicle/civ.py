"""The digest of a Throne of Tokens match: the ages of the world, its wars, treaties and conquests.

A Civ match has up to 60 rounds, most of them quiet: armies march and cities grow. The story
groups the rounds into ages (`AGE` rounds each) and tells what changed the map or the balance:
cities founded and conquered, wars declared, treaties signed and broken, the biggest battles,
rare events (plague, drought, rebellion, barbarians), public talk and the race for the gold.
Everything is read from the log as a spectator reads it; every fact keeps the `seq` of its event.
"""

from collections import Counter
from collections.abc import Iterable, Mapping
from typing import Any

from arena.chronicle.digest import Digest, Fact, Section, quote_of
from arena.engine.types import MESSAGE, Event, EventSource
from games.civ.state import NEUTRAL

AGE = 10  # rounds told as one chapter
BIG_BATTLE = 3  # units lost in a battle, both sides together, that make it worth telling
MAX_BATTLES = 2  # battles told per age (the biggest)
TOLD_EVENTS = {"plague", "drought", "rebellion", "barbarians"}  # the rest is bookkeeping


def age_of(round_no: int) -> int:
    return (round_no - 1) // AGE + 1


def build(events: Iterable[Event], names: Mapping[str, str] | None = None) -> Digest:
    """The digest of a finished Throne of Tokens match, from its whole log."""
    log = list(events)
    start = next(e for e in log if e.type == "match_started")
    seats: list[str] = list(start.data["players"])
    settings = start.data.get("settings") or {}
    won = next((e.data for e in log if e.type == "victory"), None)
    rounds = (
        won["round"]
        if won
        else max((e.data["round"] for e in log if e.type == "round_started"), default=0)
    )

    sections = [Section(kind="prologue", number=0)]
    section = sections[0]
    owner: dict[str, str] = {}  # city -> nation
    capitals: set[str] = set()
    parties: dict[str, list[str]] = {}  # treaty -> the two nations
    battles: list[Fact] = []
    founded: Counter[str] = Counter()
    founded_seq: dict[str, int] = {}
    counting: dict[str, int] = {}
    talked = False

    def add(kind: str, seq: int, **data: Any) -> None:
        section.facts.append(Fact(kind=kind, data={"seq": seq, **data}))

    def close_age() -> None:
        best = sorted(battles, key=lambda f: (-f.data["lost"], f.data["seq"]))[:MAX_BATTLES]
        section.facts.extend(best)
        for who, count in founded.items():
            section.facts.append(
                Fact(kind="founded", data={"seq": founded_seq[who], "who": who, "count": count})
            )
        battles.clear()
        founded.clear()
        founded_seq.clear()

    add("cast", 0, players=seats, rounds=settings.get("rounds", rounds))
    for seq, event in enumerate(log):
        d, t = event.data, event.type
        if event.source is EventSource.ENGINE:
            continue
        if t == "round_started":
            age = age_of(d["round"])
            if section.kind != "age" or section.number != age:
                close_age()
                section = Section(kind="age", number=age)
                sections.append(section)
                talked = False
                last = min(age * AGE, rounds) if rounds else age * AGE
                add("age_starts", seq, n=age, first=d["round"], last=last)
        elif t == "city_founded":
            if d["owner"] not in owner.values():
                capitals.add(d["city"])  # the first city of a nation is its capital
            owner[d["city"]] = d["owner"]
            if section.kind == "age":  # the capitals of the setup are in the cast
                founded[d["owner"]] += 1
                founded_seq.setdefault(d["owner"], seq)
        elif t == "city_conquered":
            owner[d["city"]] = d["to"]
            add("conquest", seq, taker=d["to"], loser=d["from"], capital=d["city"] in capitals)
        elif t == "battle":
            a, b = d["attacker"], d["defender"]
            lost = len(a.get("lost", [])) + len(b.get("lost", []))
            if lost >= BIG_BATTLE:
                battles.append(
                    Fact(
                        kind="battle",
                        data={
                            "seq": seq,
                            "attacker": a["nation"],
                            "defender": b["nation"],
                            "winner": d["winner"],
                            "lost_attacker": len(a.get("lost", [])),
                            "lost_defender": len(b.get("lost", [])),
                            "city": b.get("city") is not None,
                            "lost": lost,
                        },
                    )
                )
        elif t == "war_declared":
            add("war", seq, by=d["by"], on=d["on"], joined=list(d["joined"]))
        elif t == "treaty_signed":
            parties[d["treaty"]] = list(d["parties"])
            add(
                "treaty",
                seq,
                kind_id=d["kind"],
                a=d["parties"][0],
                b=d["parties"][1],
                ends_war=bool(d.get("ends_war")),
            )
        elif t == "treaty_broken":
            pair = parties.get(d["treaty"], [])
            other = next((p for p in pair if p != d["by"]), None)
            add("broken", seq, by=d["by"], other=other)
        elif t == "random_event" and d["event"] in TOLD_EVENTS:
            if d["event"] == "drought":
                hit = sorted(set(event.visible_to or []))
            elif d["event"] == "rebellion":
                hit = [d["from"]]
                owner[d["city"]] = NEUTRAL
            elif "city" in d:
                hit = [owner.get(d["city"], NEUTRAL)]
            else:
                hit = []
            add("event", seq, event=d["event"], nations=hit)
        elif t == "economy_countdown" and event.visible_to is None:
            for who, n in d["rounds"].items():
                if n == 1 and counting.get(who, 0) == 0:
                    add("gold_rush", seq, who=who, needed=d["needed"])
            counting = dict(d["rounds"])
        elif t == MESSAGE and event.visible_to is None and not talked:
            if quote := quote_of(d["text"], seats):
                add("talk", seq, who=d["player"], quote=quote)
                talked = True
        elif t == "victory":
            close_age()
            section = Section(kind="epilogue", number=0)
            sections.append(section)
            add("result", seq, kind_id=d["kind"], winners=list(d["winners"]), round=d["round"])
            standings = [(s["player"], s["score"]) for s in d["standings"]]
            add("ranking", seq, standings=standings)
    close_age()
    for each in sections:  # the battles and the foundings were added at the end of their age
        each.facts.sort(key=lambda f: f.data["seq"])
    digest = Digest(
        game="civ", seed=int(start.data.get("seed") or 0), seats=seats, sections=sections
    )
    digest.glance = _glance(digest, rounds)
    return digest


def _facts(digest: Digest, kind: str) -> list[Fact]:
    return [f for s in digest.sections for f in s.facts if f.kind == kind]


def _glance(digest: Digest, rounds: int) -> list[Fact]:
    glance: list[Fact] = []
    if result := next(iter(_facts(digest, "result")), None):
        glance.append(Fact(kind="winner", data=result.data))
    glance.append(Fact(kind="length", data={"rounds": rounds}))
    if turning := _turning_point(digest):
        glance.append(turning)
    taken = Counter(
        f.data["taker"] for f in _facts(digest, "conquest") if f.data["taker"] != NEUTRAL
    )
    if taken:
        who, n = min(taken.items(), key=lambda item: (-item[1], digest.seats.index(item[0])))
        glance.append(Fact(kind="conqueror", data={"who": who, "cities": n}))
    signed = Counter(p for f in _facts(digest, "treaty") for p in (f.data["a"], f.data["b"]))
    if signed:
        who, n = min(signed.items(), key=lambda item: (-item[1], digest.seats.index(item[0])))
        glance.append(Fact(kind="diplomat", data={"who": who, "treaties": n}))
    return glance


def _turning_point(digest: Digest) -> Fact | None:
    """The moment that decided the match: a fallen capital, else the biggest battle, else the
    first war; the earliest of its kind."""
    for section in digest.sections:
        for fact in section.facts:
            if fact.kind == "conquest" and fact.data["capital"]:
                return Fact(
                    kind="turning_point",
                    data={"type": "capital", "n": section.number, **_who(fact)},
                )
    battles = [(s, f) for s in digest.sections for f in s.facts if f.kind == "battle"]
    if battles:
        section, fact = max(battles, key=lambda sf: (sf[1].data["lost"], -sf[1].data["seq"]))
        return Fact(
            kind="turning_point", data={"type": "battle", "n": section.number, **_who(fact)}
        )
    for section in digest.sections:
        for fact in section.facts:
            if fact.kind == "war":
                return Fact(
                    kind="turning_point", data={"type": "war", "n": section.number, **_who(fact)}
                )
    return None


def _who(fact: Fact) -> dict[str, Any]:
    keys = ("taker", "loser", "attacker", "defender", "winner", "by", "on", "lost")
    return {k: fact.data[k] for k in keys if k in fact.data}
