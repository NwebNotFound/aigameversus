"""The digest of a Liar's Deck match: bluffs, calls, shots and the way down to the last player.

Which play was a lie and how big comes from `arena.analytics.match_analytics`; the rounds,
the calls, the reveals, the shots and the eliminations are read here from the log, and so are
the table-talk quotes. Every fact keeps the `seq` of its event.
"""

from collections.abc import Iterable, Mapping
from typing import Any

from arena.chronicle.digest import Digest, Fact, Section, quote_of
from arena.engine.types import MESSAGE, Event, EventSource

BIG_LIE = 2  # false cards in one play that make it worth telling
MAX_PLAYS = 2  # plays told per round (the biggest)
CLOSE_CALL = 1 / 3  # a shot this likely to be live, survived, is worth telling


def build(events: Iterable[Event], names: Mapping[str, str] | None = None) -> Digest:
    """The digest of a finished Liar's Deck match, from its whole log."""
    from arena.analytics import match_analytics  # late: analytics imports the chronicle's words

    log = list(events)
    start = next(e for e in log if e.type == "match_started")
    seats: list[str] = list(start.data["players"])
    analytics = match_analytics("liars_deck", log, True, names or {})
    move_at = {m["seq"]: m for m in analytics["moves"]}
    risk_at = {p["seq"]: p["risk"] for p in analytics["pulls"]}
    finished = next((e for e in log if e.type == "match_finished"), None)
    place = {p["player"]: p["rank"] for p in (finished.data["placements"] if finished else [])}

    sections = [Section(kind="prologue", number=0)]
    sections[0].facts.append(
        Fact(
            kind="cast",
            data={
                "seq": 0,
                "players": seats,
                "variant": (start.data.get("settings") or {}).get("variant"),
            },
        )
    )
    section = sections[0]
    last_play: dict[str, Any] = {}
    said: dict[str, tuple[int, str]] = {}  # a player's latest table talk this round
    candidates: list[Fact] = []
    shooters_reason = ""
    caller_seat = ""
    alive = list(seats)
    duel_told = False

    def add(kind: str, seq: int, **data: Any) -> None:
        section.facts.append(Fact(kind=kind, data={"seq": seq, **data}))

    def flush_plays() -> None:
        best = sorted(
            candidates,
            key=lambda f: (-f.data["false_cards"], -f.data["count"], f.data["seq"]),
        )[:MAX_PLAYS]
        section.facts.extend(sorted(best, key=lambda f: f.data["seq"]))
        candidates.clear()

    for seq, event in enumerate(log):
        d, t = event.data, event.type
        if event.source is EventSource.ENGINE:
            continue
        if t == "round_started":
            flush_plays()
            section = Section(kind="round", number=d["round"])
            sections.append(section)
            said, last_play = {}, {}
            alive = list(d["players"])
            add(
                "round_starts",
                seq,
                n=d["round"],
                card=d["table_card"],
                alive=len(alive),
                starter=d["starter"],
            )
            if len(alive) == 2 and not duel_told:  # the duel is announced once
                duel_told = True
                add("duel", seq, a=alive[0], b=alive[1], n=d["round"])
        elif t == MESSAGE and event.visible_to is None:
            said[d["player"]] = (seq, d["text"])
        elif t == "cards_played":
            move = move_at.get(seq)
            last_play = {"player": d["player"], "count": d["count"], "move": move, "seq": seq}
            if move and move["kind"] == "play":
                false_cards = move["false_cards"]
                kind = "lie_big" if false_cards >= BIG_LIE else "truth_big"
                if false_cards >= BIG_LIE or d["count"] >= 3:
                    candidates.append(
                        Fact(
                            kind=kind,
                            data={
                                "seq": seq,
                                "who": d["player"],
                                "count": d["count"],
                                "false_cards": false_cards,
                            },
                        )
                    )
        elif t == "liar_called":
            caller_seat = d["caller"]
            target_said = said.get(d["target"])
            if target_said and (quote := quote_of(target_said[1], seats, prefer_mention=False)):
                add("claim_quote", target_said[0], who=d["target"], quote=quote)
            call_said = said.get(d["caller"])
            later = call_said and call_said[0] > (target_said[0] if target_said else -1)
            if later and (quote := quote_of(call_said[1], seats, prefer_mention=False)):
                add("claim_quote", call_said[0], who=d["caller"], quote=quote)
            add("call", seq, caller=d["caller"], target=d["target"], automatic=d["automatic"])
        elif t == "cards_revealed":
            move = (last_play or {}).get("move") or {}
            add(
                "reveal",
                seq,
                target=d["player"],
                caller=caller_seat,
                cards=list(d["cards"]),
                honest=d["honest"],
                devil=d["devil"],
                n_false=move.get("false_cards", 0),
            )
        elif t == "shooters_chosen":
            shooters_reason = d["reason"]
            if d["reason"] == "devil":
                add("devil_shots", seq, players=list(d["players"]))
        elif t == "trigger_pulled":
            risk = risk_at.get(seq, 0.0)
            add(
                "trigger",
                seq,
                player=d["player"],
                pull=d["pull"],
                live=d["live"],
                risk=risk,
                reason=shooters_reason,
            )
        elif t == "players_eliminated":
            for player in d["players"]:
                add("eliminated", seq, player=player, place=place.get(player), n=section.number)
        elif t == "match_over":
            flush_plays()
            section = Section(kind="epilogue", number=0)
            sections.append(section)
            ranking = [p for p, _ in sorted(place.items(), key=lambda item: item[1])]
            rounds = sum(1 for s in sections if s.kind == "round")
            add("result", seq, winner=d["winner"], rounds=rounds)
            add("ranking", seq, ranking=ranking)
    flush_plays()
    for each in sections:  # the highlight plays were added at the end of their round
        each.facts.sort(key=lambda f: f.data["seq"])
    digest = Digest(
        game="liars_deck", seed=int(start.data.get("seed") or 0), seats=seats, sections=sections
    )
    digest.glance = _glance(digest, analytics)
    return digest


def _glance(digest: Digest, analytics: dict[str, Any]) -> list[Fact]:
    glance: list[Fact] = []
    result = next((f for s in digest.sections for f in s.facts if f.kind == "result"), None)
    if result:
        glance.append(Fact(kind="winner", data=result.data))
        glance.append(Fact(kind="length", data={"rounds": result.data["rounds"]}))
    if turning := _turning_point(digest):
        glance.append(turning)
    totals = analytics["totals"]
    bluffer = max(
        ((p, t) for p, t in totals.items() if t["plays"] >= 3 and t["lies"] >= 2),
        key=lambda item: (item[1]["lies"], item[1]["plays"], item[0]),
        default=None,
    )
    if bluffer:
        who, t = bluffer
        glance.append(
            Fact(kind="bluffer", data={"who": who, "lies": t["lies"], "plays": t["plays"]})
        )
    callers = [
        (p, t["call_accuracy"])
        for p, t in totals.items()
        if t["call_accuracy"]["of"] >= 2 and t["call_accuracy"]["n"] >= 2
    ]
    if callers:
        who, rate = max(callers, key=lambda item: (item[1]["value"], item[1]["of"], item[0]))
        glance.append(Fact(kind="caller", data={"who": who, "right": rate["n"], "of": rate["of"]}))
    lucky = max(totals.items(), key=lambda item: (item[1]["pulls_survived"], item[0]), default=None)
    if lucky and lucky[1]["pulls_survived"] >= 2:
        glance.append(
            Fact(kind="survivor", data={"who": lucky[0], "shots": lucky[1]["pulls_survived"]})
        )
    return glance


def _turning_point(digest: Digest) -> Fact | None:
    """The moment that decided the match, by a fixed ranking of what matters most."""
    best: tuple[int, Fact] | None = None

    def consider(score: int, kind: str, **data: Any) -> None:
        nonlocal best
        if best is None or score >= best[0]:
            best = (score, Fact(kind="turning_point", data={"type": kind, **data}))

    for section in digest.sections:
        facts = section.facts
        for index, fact in enumerate(facts):
            d = fact.data
            if fact.kind == "trigger" and not d["live"] and d["risk"] >= 0.5:
                consider(6, "coin_flip", n=section.number, player=d["player"], risk=d["risk"])
            elif fact.kind == "devil_shots":
                consider(6, "devil", n=section.number, seq=d["seq"])
            elif fact.kind == "reveal" and not d["honest"] and d["n_false"] >= BIG_LIE:
                consider(
                    5,
                    "big_lie_caught",
                    n=section.number,
                    target=d["target"],
                    caller=d["caller"],
                    count=d["n_false"],
                    seq=d["seq"],
                )
            elif fact.kind == "eliminated" and d["place"] == 2:
                shots = [f for f in facts[:index] if f.kind == "reveal"]
                kind = "final_duel" if shots else "final_shot"
                consider(
                    4,
                    kind,
                    n=section.number,
                    loser=d["player"],
                    winner=_result_winner(digest),
                    seq=d["seq"],
                )
            elif fact.kind == "reveal" and d["honest"] and _caller_died(facts, index):
                consider(
                    4,
                    "wrong_call_fatal",
                    n=section.number,
                    caller=d["caller"],
                    target=d["target"],
                    seq=d["seq"],
                )
    return best[1] if best else None


def _result_winner(digest: Digest) -> str | None:
    result = next((f for s in digest.sections for f in s.facts if f.kind == "result"), None)
    return result.data["winner"] if result else None


def _caller_died(facts: list[Fact], index: int) -> bool:
    """Whether the player who made a wrong call was eliminated in the same round."""
    caller = facts[index].data["caller"]
    return any(f.kind == "eliminated" and f.data["player"] == caller for f in facts[index:])
