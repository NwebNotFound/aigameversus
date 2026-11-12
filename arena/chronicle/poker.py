"""The digest of a Poker match: the blind levels of the tournament, its big pots and its busts.

A tournament plays up to 100 hands, most of them small: blinds, a raise, everyone folds. The
story tells one chapter per blind level (the blinds double every `double_every` hands) and in
it what moved the chips: the biggest pots (who won, with what, whether anyone was all in or
it was a bluff), the players who busted, and one line of table talk. Hole cards are in the
spectator log, so a pot won without a showdown can be told as the bluff it was. Every fact
keeps the `seq` of its event.
"""

from collections import Counter
from collections.abc import Iterable, Mapping
from typing import Any

from arena.chronicle.digest import Digest, Fact, Section, quote_of
from arena.engine.types import MESSAGE, Event, EventSource
from games.poker.cards import Card
from games.poker.evaluator import HandCategory, best_hand

BIG_POT = 10  # a pot of at least this many big blinds is worth telling
MAX_POTS = 2  # pots told per blind level (the biggest)
DOUBLE_EVERY = 10  # the plugin's default, for a log whose settings do not say
AGGRESSOR_MOVES = 3  # raises and all-ins that make a player the table's aggressor


def build(events: Iterable[Event], names: Mapping[str, str] | None = None) -> Digest:
    """The digest of a finished Poker match, from its whole log."""
    log = list(events)
    start = next(e for e in log if e.type == "match_started")
    seats: list[str] = list(start.data["players"])
    settings = start.data.get("settings") or {}
    double_every = int(settings.get("double_every") or DOUBLE_EVERY)
    finished = next((e for e in log if e.type == "match_finished"), None)
    place = {p["player"]: p["rank"] for p in (finished.data["placements"] if finished else [])}

    sections = [Section(kind="prologue", number=0)]
    section = sections[0]
    pots: list[Fact] = []
    hand: dict[str, Any] = {}
    aggression: Counter[str] = Counter()
    hands_played = 0
    talked = False

    def add(kind: str, seq: int, **data: Any) -> None:
        section.facts.append(Fact(kind=kind, data={"seq": seq, **data}))

    def close_level() -> None:
        best = sorted(pots, key=lambda f: (-f.data["amount"], f.data["seq"]))[:MAX_POTS]
        section.facts.extend(best)
        pots.clear()

    stack = int(settings.get("starting_stack") or 1000)
    add("cast", 0, players=seats, stack=stack, hands=int(settings.get("hand_limit") or 100))
    for seq, event in enumerate(log):
        d, t = event.data, event.type
        if event.source is EventSource.ENGINE:
            continue
        if t == "hand_started":
            hands_played = d["hand"]
            level = (d["hand"] - 1) // double_every + 1
            if section.kind != "level" or section.number != level:
                close_level()
                section = Section(kind="level", number=level)
                sections.append(section)
                talked = False
                add(
                    "level_starts",
                    seq,
                    n=level,
                    first=d["hand"],
                    small=d.get("small_blind", d["big_blind"] // 2),
                    big=d["big_blind"],
                    players=len(d["players"]),
                )
            hand = {
                "n": d["hand"],
                "seq": seq,
                "big": d["big_blind"],
                "holes": {},
                "board": [],
                "pots": [],
                "shown": {},
                "allin": [],
                "raised": set(),
            }
        elif t == "hole_dealt":
            hand["holes"][d["player"]] = list(d["cards"])
        elif t == "street_started":
            hand["board"] += list(d["cards"])
        elif t == "bet_action":
            if d["kind"] in ("raise", "all_in"):
                aggression[d["player"]] += 1
                hand["raised"].add(d["player"])
            if d["kind"] == "all_in":
                hand["allin"].append(d["player"])
        elif t == "showdown":
            hand["shown"] = {h["player"]: h["hand"] for h in d["hands"]}
        elif t == "pot_awarded":
            hand["pots"].append(d)
        elif t == "hand_ended" and hand:
            if fact := _pot_fact(hand, d["showdown"], seq):
                pots.append(fact)
        elif t == "players_eliminated":
            for player in d["players"]:
                add("busted", seq, player=player, place=place.get(player), hand=hand.get("n"))
        elif t == MESSAGE and event.visible_to is None and not talked:
            if quote := quote_of(d["text"], seats):
                add("talk", seq, who=d["player"], quote=quote)
                talked = True
        elif t == "match_over":
            close_level()
            section = Section(kind="epilogue", number=0)
            sections.append(section)
            leaders = [p for p, rank in place.items() if rank == 1]
            add("result", seq, winner=d["winner"], leaders=leaders, hands=hands_played)
            ranking = [p for p, _ in sorted(place.items(), key=lambda item: item[1])]
            add("ranking", seq, ranking=ranking)
    close_level()
    for each in sections:  # the pots were added at the end of their level
        each.facts.sort(key=lambda f: f.data["seq"])
    digest = Digest(
        game="poker", seed=int(start.data.get("seed") or 0), seats=seats, sections=sections
    )
    digest.glance = _glance(digest, hands_played, aggression)
    return digest


def _pot_fact(hand: dict[str, Any], showdown: bool, seq: int) -> Fact | None:
    """The fact of one hand's pot, if it was big enough to tell.

    A pot only one player could win is either the whole pot of a hand everyone else folded,
    or a bet nobody called coming back; next to contested pots it is the latter.
    """
    contested = [p for p in hand["pots"] if len(p["eligible"]) > 1]
    counted = contested or hand["pots"]
    amount = sum(p["amount"] for p in counted)
    if amount < BIG_POT * hand["big"]:
        return None
    won: Counter[str] = Counter()
    for pot in counted:
        for player, share in pot["shares"].items():
            won[player] += share
    winner = min(won, key=lambda p: (-won[p], p))
    shown = hand["shown"]
    losers = [p for p in shown if p != winner]
    best_loser = max(losers, key=lambda p: HandCategory[shown[p].upper()], default=None)
    data: dict[str, Any] = {
        "seq": hand["seq"],
        "hand": hand["n"],
        "winner": winner,
        "split": len([p for p in won if won[p] > 0]) > 1,
        "amount": amount,
        "big_blinds": amount // hand["big"],
        "showdown": showdown,
        "with": shown.get(winner),
        "loser": best_loser,
        "loser_with": shown.get(best_loser) if best_loser else None,
        "allin": sorted(set(hand["allin"])),
        "bluff": not showdown and _nothing(hand, winner) and winner in hand["raised"],
    }
    return Fact(kind="pot", data=data)


def _nothing(hand: dict[str, Any], player: str) -> bool:
    """Whether the player held no pair or better with the board as it lay (a bluff)."""
    cards = hand["holes"].get(player, []) + hand["board"]
    if len(hand["board"]) < 3 or len(cards) < 5:
        return False  # before the flop a hand is a hope, not a bluff
    return best_hand([Card.parse(c) for c in cards]).category is HandCategory.HIGH_CARD


def _facts(digest: Digest, kind: str) -> list[tuple[Section, Fact]]:
    return [(s, f) for s in digest.sections for f in s.facts if f.kind == kind]


def _glance(digest: Digest, hands: int, aggression: Counter[str]) -> list[Fact]:
    glance: list[Fact] = []
    if result := next(iter(_facts(digest, "result")), None):
        glance.append(Fact(kind="winner", data=result[1].data))
    glance.append(Fact(kind="length", data={"hands": hands}))
    pots = _facts(digest, "pot")
    if pots:
        section, pot = max(pots, key=lambda sf: (sf[1].data["amount"], -sf[1].data["seq"]))
        glance.append(Fact(kind="turning_point", data={"level": section.number, **pot.data}))
    shown = [
        (HandCategory[f.data["with"].upper()], f.data)
        for _, f in pots
        if f.data["showdown"] and f.data["with"]
    ]
    if shown:
        category, best = max(shown, key=lambda item: (item[0], -item[1]["seq"]))
        if category >= HandCategory.TWO_PAIR:
            glance.append(
                Fact(kind="best_hand", data={"who": best["winner"], "with": best["with"]})
            )
    if aggression:
        who, moves = min(aggression.items(), key=lambda item: (-item[1], item[0]))
        if moves >= AGGRESSOR_MOVES:
            glance.append(Fact(kind="aggressor", data={"who": who, "moves": moves}))
    return glance
