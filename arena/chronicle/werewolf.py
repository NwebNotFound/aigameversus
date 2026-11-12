"""The digest of a Werewolf match: nights, days, claims, accusations, votes and turning points.

The numbers that need reading what players said (claims, accusations, how right each voter
was) come from `arena.analytics.match_analytics`; the night, the deaths, the captain and the
quotes are read here from the log. Every fact keeps the `seq` of its event (the position in
the whole log) so a report can jump a replay to it.
"""

from collections import Counter
from collections.abc import Iterable, Mapping
from typing import Any

from arena.chronicle.digest import Digest, Fact, Section, quote_of
from arena.engine.types import MESSAGE, Event, EventSource
from games.werewolf.selection import load_roles

SPECIAL_CAUSES = ("wolves", "poison", "white_wolf", "caught_spying", "grief")


def _team(role: str | None) -> str | None:
    return load_roles()[role].team if role in load_roles() else None


def build(events: Iterable[Event], names: Mapping[str, str] | None = None) -> Digest:
    """The digest of a finished Werewolf match, from its whole log."""
    from arena.analytics import match_analytics  # late: analytics imports the chronicle's words

    log = list(events)
    start = next(e for e in log if e.type == "match_started")
    seats: list[str] = list(start.data["players"])
    analytics = match_analytics("werewolf", log, True, names or {})
    roles: dict[str, str] = analytics["meta"]["roles"] or {}
    text_at = {seq: e.data["text"] for seq, e in enumerate(log) if e.type == MESSAGE}
    sections: list[Section] = []
    section = Section(kind="prologue", number=0)
    sections.append(section)
    facts = section.facts
    alive = list(seats)
    last_wolf_vote: dict[str, str] = {}
    night: dict[str, Any] = {}
    day_messages: list[tuple[int, str, str]] = []  # seq, player, text of this day
    pack: list[str] = []

    def add(kind: str, seq: int, **data: Any) -> None:
        facts.append(Fact(kind=kind, data={"seq": seq, **data}))

    for seq, event in enumerate(log):
        d = event.data
        if event.source is EventSource.ENGINE:
            continue
        t = event.type
        if t == "roles_dealt":
            add(
                "cast",
                seq,
                players=[{"seat": s, "role": roles.get(s)} for s in seats],
                selection=d["selection"],
            )
        elif t == "pack_revealed":
            pack = list(d["wolves"])
        elif t == "lovers_linked":
            add("lovers", seq, pair=list(d["lovers"]), by=d["player"])
        elif t == "night_started":
            section = Section(kind="night", number=d["night"])
            sections.append(section)
            facts = section.facts
            night = {"saved": None, "guarded": None, "plan": None, "target_votes": Counter()}
            last_wolf_vote = {}
            add("night_falls", seq, n=d["night"], alive=len(alive))
        elif t == "wolf_vote":
            last_wolf_vote[d["player"]] = d["target"]
            night["target_votes"][d["target"]] += 1
        elif t == MESSAGE and event.visible_to is not None and section.kind == "night":
            if night.get("plan") is None and d["player"] in pack:
                quote = quote_of(d["text"], seats)
                if quote:
                    night["plan"] = True
                    add("wolf_plan", seq, who=d["player"], quote=quote)
        elif t == "seer_inspected":
            wolf = _team(d["role"]) == "wolves"
            add("seer_look", seq, seer=d["player"], target=d["target"], role=d["role"], wolf=wolf)
        elif t == "protected":
            night["guarded"] = (d["player"], d["target"])
        elif t == "witch_acted":
            if d.get("healed"):
                night["saved"] = d["healed"]
                add("witch_heal", seq, witch=d["player"], target=d["healed"])
            if d.get("poisoned"):
                add("witch_poison", seq, witch=d["player"], target=d["poisoned"])
        elif t == "morning_started":
            target = (night.get("target_votes") or Counter()).most_common(1)
            victim = target[0][0] if target else None
            if victim and victim not in d["deaths"]:
                guard = night.get("guarded")
                saved_by = (
                    "witch"
                    if night.get("saved") == victim
                    else "protector"
                    if guard and guard[1] == victim
                    else None
                )
                add("wolf_missed", seq, target=victim, saved_by=saved_by)
            elif victim:
                add("wolf_target", seq, target=victim)
            if not d["deaths"]:
                add("night_quiet", seq)
        elif t == "player_died":
            if d["player"] in alive:
                alive.remove(d["player"])
            if d["cause"] != "executed":
                add("death", seq, player=d["player"], role=d["role"], cause=d["cause"])
        elif t == "hunter_shot":
            add("hunter_shot", seq, hunter=d["player"], target=d["target"])
        elif t == "day_started":
            section = Section(kind="day", number=d["day"])
            sections.append(section)
            facts = section.facts
            day_messages = []
            add("day_breaks", seq, n=d["day"], alive=len(alive), speakers=len(d["order"]))
        elif t == "captain_elected":
            votes = d["votes"]
            add("captain", seq, player=d["player"], votes=votes.get(d["player"], 0), field=votes)
        elif t == MESSAGE and event.visible_to is None:
            day_messages.append((seq, d["player"], d["text"]))
        elif t == "vote_result":
            _day_facts(
                add,
                d,
                seq,
                seats,
                roles,
                analytics,
                text_at,
                day_messages,
            )
            day_messages = []
        elif t == "game_over":
            section = Section(kind="epilogue", number=0)
            sections.append(section)
            facts = section.facts
            days = sum(1 for s_ in sections if s_.kind == "day")
            add("result", seq, winner=d["winner"], winners=list(d["winners"]), days=days)
            add(
                "reveal",
                seq,
                players=[{"seat": s, "role": roles.get(s), "alive": s in alive} for s in seats],
            )
        elif t == "love_revealed":
            pass
    _claims(sections, analytics, roles, seats)
    digest = Digest(
        game="werewolf", seed=int(start.data.get("seed") or 0), seats=seats, sections=sections
    )
    digest.glance = _glance(digest, analytics, roles)
    return digest


def _day_facts(add, d, seq, seats, roles, analytics, text_at, day_messages) -> None:
    day = d["day"]
    tally = sorted(d["counts"].items(), key=lambda item: (-item[1], item[0]))
    executed = d.get("executed")
    votes = next((x for x in analytics["votes"]["days"] if x["day"] == day), {"votes": {}})
    stance = analytics["stance"]
    # Why they voted: the reason a player gave with the vote, verbatim, shortened.
    reasons = []
    for vote_seq, entry in sorted(stance.items()):
        reason_seq = entry.get("reason_seq")
        if reason_seq is None or entry.get("votes_for") is None:
            continue
        if not (day_messages and day_messages[0][0] <= vote_seq <= seq):
            continue
        quote = quote_of(text_at[reason_seq], seats, prefer_mention=False)
        if quote:
            reasons.append((entry["votes_for"] != executed, vote_seq, entry["player"], quote))
    for _, vote_seq, voter, quote in sorted(reasons)[:2]:
        add("vote_reason", vote_seq, who=voter, target=votes["votes"].get(voter), quote=quote)
    focus = executed or (tally[0][0] if tally else None)
    for who, quote_seq, quote in _speech_quotes(day_messages, focus, seats):
        add("speech", quote_seq, who=who, quote=quote, focus=focus)
    add("tally", seq, counts=tally, executed=executed, voters=votes["votes"])
    if executed:
        role = roles.get(executed)
        add(
            "execution",
            seq,
            player=executed,
            role=role,
            team=_team(role),
            votes=d["counts"].get(executed, 0),
            unanimous=len(set(v for v in votes["votes"].values() if v)) == 1
            and sum(1 for v in votes["votes"].values() if v) >= 3,
        )
    else:
        add("no_execution", seq)


def _speech_quotes(messages, focus, seats) -> list[tuple[str, int, str]]:
    """Up to two short quotes: the focus player's own words, and the first who named them."""
    out: list[tuple[str, int, str]] = []
    used: set[str] = set()
    if focus:
        own = [m for m in messages if m[1] == focus]
        for seq, who, text in reversed(own):
            if quote := quote_of(text, seats, prefer_mention=False):
                out.append((who, seq, quote))
                used.add(who)
                break
    for seq, who, text in messages:
        if who in used or not focus or focus.lower() not in text.lower():
            continue
        if quote := quote_of(text, seats):
            out.append((who, seq, quote))
            break
    return out


def _section_at(sections: list[Section], analytics, seq: int) -> Section:
    """The night or day section whose phase holds this seq (the last phase starting before it)."""
    phases = analytics["phases"]
    kind, number = "prologue", 0
    for phase in phases:
        if phase["from_seq"] <= seq:
            kind, number = phase["kind"], phase["number"]
    for section in sections:
        if section.kind == kind and section.number == number:
            return section
    return sections[0]


def _claims(sections: list[Section], analytics, roles: dict[str, str], seats) -> None:
    """Role claims: the lies (claimed role is not the real one), the special roles claimed,
    and the roles two players claimed at once."""
    done: set[tuple[str, str]] = set()
    for claim in analytics["claims"]:
        who, role = claim["player"], claim["role"]
        actual = roles.get(who)
        if (who, role) in done or actual is None:
            continue
        done.add((who, role))
        section = _section_at(sections, analytics, claim["seq"])
        data = {"seq": claim["seq"], "who": who, "claimed": role, "actual": actual}
        if role != actual:
            section.facts.append(Fact(kind="claim_lie", data=data))
        elif role != "villager":
            section.facts.append(Fact(kind="claim_true", data=data))
        if claim["counterclaimed_by"]:
            section.facts.append(
                Fact(
                    kind="counterclaim",
                    data={
                        "seq": claim["seq"],
                        "role": role,
                        "claimants": sorted([who, *claim["counterclaimed_by"]]),
                        "real": next((s for s in seats if roles.get(s) == role), None),
                    },
                )
            )


def _glance(digest: Digest, analytics, roles: dict[str, str]) -> list[Fact]:
    glance: list[Fact] = []
    result = next(
        (f for s in digest.sections for f in s.facts if f.kind == "result"),
        None,
    )
    days = sum(1 for s in digest.sections if s.kind == "day")
    if result:
        glance.append(Fact(kind="winner", data=result.data | {"days": days}))
    glance.append(Fact(kind="length", data={"days": days}))
    turning = _turning_point(digest, roles)
    if turning:
        glance.append(turning)
    best = _most_accurate(analytics)
    if best:
        glance.append(best)
    sly = _most_deceptive(digest, roles)
    if sly:
        glance.append(sly)
    return glance


def _turning_point(digest: Digest, roles: dict[str, str]) -> Fact | None:
    """The moment that decided the match, by a fixed order of what matters most."""
    best: tuple[int, Fact] | None = None
    for section in digest.sections:
        for fact in section.facts:
            data, score, kind = fact.data, 0, None
            if fact.kind == "execution":
                if data["team"] == "village":
                    special = data["role"] not in (None, "villager")
                    kind, score = "wrong_execution", 4 + (2 if special else 0)
                elif data["team"] == "wolves":
                    kind, score = "wolf_executed", 3
            elif fact.kind == "death" and data["role"] == "seer" and data["cause"] == "wolves":
                kind, score = "seer_killed", 6
            elif fact.kind == "death" and data["cause"] == "grief":
                kind, score = "lover_grief", 5
            elif fact.kind == "hunter_shot":
                kind, score = "hunter_shot", 4
            elif fact.kind == "claim_lie" and data["claimed"] in ("seer", "witch", "hunter"):
                kind, score = "false_claim", 5
            elif fact.kind == "wolf_missed" and data["saved_by"]:
                kind, score = "save", 3
            if kind and (best is None or score >= best[0]):
                fact_data = {"type": kind, "n": section.number, "phase": section.kind, **data}
                best = (score, Fact(kind="turning_point", data=fact_data))
    return best[1] if best else None


def _most_accurate(analytics) -> Fact | None:
    accuracy = analytics["votes"]["accuracy"] or {}
    ranked = sorted(
        ((v["n"] / v["of"], v["of"], p, v) for p, v in accuracy.items() if v["of"] >= 2),
        key=lambda item: (-item[0], -item[1], item[2]),
    )
    if not ranked or ranked[0][0] == 0:
        return None
    _, _, who, value = ranked[0]
    return Fact(kind="accurate_voter", data={"who": who, "right": value["n"], "of": value["of"]})


def _most_deceptive(digest: Digest, roles: dict[str, str]) -> Fact | None:
    """The wolf who lasted longest, with the lies they told on the way."""
    lies: Counter[str] = Counter()
    for section in digest.sections:
        for fact in section.facts:
            if fact.kind == "claim_lie":
                lies[fact.data["who"]] += 1
    death_day: dict[str, int] = {}
    count = 0
    for section in digest.sections:
        if section.kind == "day":
            count = section.number
        for fact in section.facts:
            if fact.kind in ("death", "execution"):
                death_day[fact.data["player"]] = count
    last = max([s.number for s in digest.sections if s.kind == "day"] or [0])
    wolves = [s for s in digest.seats if _team(roles.get(s)) == "wolves"]
    if not wolves:
        return None
    ranked = sorted(wolves, key=lambda s: (-death_day.get(s, last + 1), -lies[s], s))
    who = ranked[0]
    return Fact(
        kind="deceptive",
        data={
            "who": who,
            "days": death_day.get(who, last + 1) if who in death_day else last,
            "survived": who not in death_day,
            "lies": lies[who],
        },
    )
