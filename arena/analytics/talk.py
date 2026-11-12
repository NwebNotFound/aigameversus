"""Table talk against the engine's ground truth: what a player said about their cards or role, and
whether it was true. No model is asked; the engine knows the hands and the roles.

    talk_checks("liars_deck", log, spoilers=True)

A check is made only where a sentence can be read with a pattern ("I have no kings", "I'm being
honest", "I have a flush", "I am the seer"), so it never judges tone or plans. Each check is a
tag with its evidence, marked `heuristic` because the words were read by rules; a sentence the
patterns miss is simply not checked. English only, like the prompts. Questions are never
checked, and neither are statements of others.

Spoilers: the true hands live in hidden events. Without `spoilers` Liar's Deck and Poker give
no tags, and Werewolf only the claims that a death has disproved. The tags are research data,
not a verdict on the player.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from arena.engine.types import MESSAGE, Event, PlayerId

Log = list[tuple[int, Event]]

NUMBERS = {
    "no": 0, "zero": 0, "none": 0, "one": 1, "a": 1, "an": 1, "single": 1,
    "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
}  # fmt: skip
SENTENCE = re.compile(r"(?<=[.!;\n])\s+")
MAX_QUOTE_WORDS = 25


def _number(word: str) -> int:
    return int(word) if word.isdigit() else NUMBERS[word]


def _sentences(text: str) -> list[str]:
    """The sentences of a speech that are statements: a question is not a claim."""
    return [s.strip() for s in SENTENCE.split(text) if s.strip() and "?" not in s]


def _quote(sentence: str) -> str:
    words = sentence.split()
    return " ".join(words[:MAX_QUOTE_WORDS]) + (" ..." if len(words) > MAX_QUOTE_WORDS else "")


def _tag(seq: int, player: PlayerId, kind: str, sentence: str, claim: str, ok: bool, why: str):
    return {
        "seq": seq,
        "player": player,
        "kind": kind,
        "quote": _quote(sentence),
        "claim": claim,
        "verdict": "true" if ok else "false",
        "evidence": why,
        "heuristic": True,
    }


# --- Liar's Deck ----------------------------------------------------------------------

RANK = r"(?P<r>king|queen|ace|joker)s?"
HOLD = re.compile(
    r"\bi(?:'ve|'m| am)?\s+(?P<only>only |just )?(?:have got|have|hold|holding|got|left with)\s+"
    rf"(?P<only2>only |just )?(?P<n>no|zero|one|two|three|four|five|six|a|an|\d)\s+{RANK}\b"
    r"(?P<tail>[^.!,;]*)",
    re.I,
)
HOLD_NOT = re.compile(
    r"\bi(?:'m| am)? (?:do not|don't|dont|haven't|have not|out of)\s*"
    rf"(?:have |hold |got )?(?:any |more )?{RANK}\b",
    re.I,
)
HONEST = re.compile(
    r"\bi(?:'m| am)\s+(?:being |totally |completely |really |actually )?"
    r"(?:honest|truthful|telling the truth|not lying|not bluffing|not a liar)\b"
    r"|\bi(?:'m| am| was)\s+not\s+(?:lying|bluffing)\b"
    r"|\bi\s+(?:play|played|am playing|'m playing)\s+(?:it\s+)?(?:honestly|straight)\b"
    r"|\bno\s+(?:lie|bluff)\b",
    re.I,
)
PLAYS = re.compile(
    r"\b(?:play(?:ing)?|put(?:ting)?|lay(?:ing)?|here (?:are|is|come)|these (?:are|is)|"
    r"coming|throw(?:ing)?|giving)\b[^.!]*?"
    rf"\b(?P<n>one|two|three|four|five|a|an|\d)\s+{RANK}\b",
    re.I,
)


def _hold_claims(sentence: str) -> list[tuple[str, int, bool, str]]:
    """(rank, count, exact, reading) for each statement about the hand in a sentence."""
    found = []
    for match in HOLD.finditer(sentence):
        n = _number(match.group("n").lower())
        exact = bool(match.group("only") or match.group("only2")) or n == 0
        exact = exact or "left" in (match.group("tail") or "").lower()
        found.append((match.group("r").lower(), n, exact, match.group(0)))
    for match in HOLD_NOT.finditer(sentence):
        found.append((match.group("r").lower(), 0, True, match.group(0)))
    return found


def _liars_deck(log: Log) -> list[dict[str, Any]]:
    from games.liars_deck.plugin import JOKER, card_rank

    tags: list[dict[str, Any]] = []
    hands: dict[PlayerId, list[str]] = {}
    table_card: str | None = None
    pending: dict[PlayerId, tuple[int, str]] = {}  # the last words of a player before their play
    for seq, event in log:
        data = event.data
        if event.type == "round_started":
            table_card, hands, pending = data["table_card"], {}, {}
        elif event.type == "hand_dealt":
            hands[data["player"]] = list(data["cards"])
        elif event.type == MESSAGE:
            player, text = data["player"], data["text"]
            pending[player] = (seq, text)
            hand = hands.get(player)
            if hand is None:
                continue
            for sentence in _sentences(text):
                for rank, count, exact, _ in _hold_claims(sentence):
                    have = sum(card_rank(card) == rank for card in hand)
                    ok = have == count if exact else have >= count
                    claim = f"holds {'exactly ' if exact else 'at least '}{count} {rank}(s)"
                    why = f"hand: {', '.join(hand) or 'empty'} ({have} {rank})"
                    tags.append(_tag(seq, player, "hand_claim", sentence, claim, ok, why))
        elif event.type == "cards_hidden":
            player, cards = data["player"], list(data["cards"])
            said = pending.pop(player, None)
            hand = hands.get(player, [])
            for card in cards:
                if card in hand:
                    hand.remove(card)
            if said is None or table_card is None:
                continue
            seq_said, text = said
            honest = all(card_rank(card) in (table_card, JOKER) for card in cards)
            played = f"played {', '.join(cards)} (table card: {table_card})"
            for sentence in _sentences(text):
                if HONEST.search(sentence):
                    tags.append(
                        _tag(seq_said, player, "honesty_claim", sentence, "this play is honest",
                             honest, played)
                    )  # fmt: skip
                elif match := PLAYS.search(sentence):
                    n, rank = _number(match.group("n").lower()), match.group("r").lower()
                    ok = n == len(cards) and rank in (table_card, JOKER) and honest
                    claim = f"played {n} {rank}(s)"
                    tags.append(_tag(seq_said, player, "play_claim", sentence, claim, ok, played))
        elif event.type == "liar_called":
            pending.pop(data["caller"], None)
    return tags


# --- Poker ----------------------------------------------------------------------------

CATEGORY_WORDS = (
    ("royal flush", 9), ("straight flush", 8), ("four of a kind", 7), ("quads", 7),
    ("full house", 6), ("a boat", 6), ("flush", 5), ("straight", 4),
    ("three of a kind", 3), ("trips", 3), ("a set", 3), ("two pair", 2), ("two pairs", 2),
    ("a pair", 1), ("one pair", 1), ("top pair", 1), ("pocket pair", 1),
)  # fmt: skip
NOTHING = re.compile(r"\b(?:nothing|air|garbage|trash|missed|a weak hand|no hand)\b", re.I)
HAVE = re.compile(
    r"\bi(?:'ve| have)?\s*(?:am |'m )?(?:have|hold|holding|got|have got|made|flopped|hit|"
    r"turned|rivered|'ve got)\b(?P<what>[^.!;]*)",
    re.I,
)
CATEGORY_NAMES = {
    0: "high card", 1: "one pair", 2: "two pair", 3: "three of a kind", 4: "straight",
    5: "flush", 6: "full house", 7: "four of a kind", 8: "straight flush", 9: "royal flush",
}  # fmt: skip


def _rank_category(cards: list) -> int:
    """The category of the best hand that rank counts alone can tell (fewer than five cards)."""
    from collections import Counter

    counts = sorted(Counter(card.rank for card in cards).values(), reverse=True)
    if counts[0] >= 4:
        return 7
    if counts[0] == 3 and len(counts) > 1 and counts[1] >= 2:
        return 6
    if counts[0] == 3:
        return 3
    if counts[0] == 2 and len(counts) > 1 and counts[1] == 2:
        return 2
    return 1 if counts[0] == 2 else 0


def _category(cards: list) -> int:
    from games.poker.evaluator import best_hand

    return int(best_hand(cards).category) if len(cards) >= 5 else _rank_category(cards)


def _hole_in_made_hand(hole: list, board: list) -> bool:
    """Does a hole card take part in a pair or better (a board pair alone is no hand)?"""
    from collections import Counter

    from games.poker.evaluator import best_hand

    counts = Counter(card.rank for card in [*hole, *board])
    if any(counts[card.rank] >= 2 for card in hole):
        return True
    if len(hole) + len(board) >= 5:
        best = best_hand([*hole, *board])
        return int(best.category) >= 4 and any(card in best.cards for card in hole)
    return False


def _poker(log: Log) -> list[dict[str, Any]]:
    from games.poker.cards import Card

    tags: list[dict[str, Any]] = []
    holes: dict[PlayerId, list] = {}
    board: list = []
    for seq, event in log:
        data = event.data
        if event.type == "hand_started":
            holes, board = {}, []
        elif event.type == "hole_dealt":
            holes[data["player"]] = [Card.parse(c) for c in data["cards"]]
        elif event.type == "street_started":
            board += [Card.parse(c) for c in data["cards"]]
        elif event.type == MESSAGE:
            player, hole = data["player"], holes.get(data["player"])
            if hole is None:
                continue
            shown = f"hole {' '.join(map(str, hole))}; board {' '.join(map(str, board)) or '-'}"
            for sentence in _sentences(data["text"]):
                tag = _poker_claim(seq, player, sentence, hole, board, shown)
                if tag:
                    tags.append(tag)
    return tags


def _poker_claim(seq, player, sentence, hole, board, shown) -> dict[str, Any] | None:
    lowered = sentence.lower()
    if re.search(r"\bpocket (?:aces|kings|queens|jacks|tens|\w+s)\b", lowered) and HAVE.search(
        sentence
    ):
        ok = hole[0].rank == hole[1].rank
        return _tag(seq, player, "poker_hand_claim", sentence, "has a pocket pair", ok, shown)
    have = HAVE.search(sentence)
    if have:
        what = have.group("what").lower()
        if NOTHING.search(what) and not re.search(r"\b(?:something|a hand)\b", what):
            ok = not _hole_in_made_hand(hole, board)
            return _tag(seq, player, "poker_hand_claim", sentence, "has nothing", ok, shown)
        for words, category in CATEGORY_WORDS:
            if re.search(rf"\b{re.escape(words)}\b", what):
                actual = _category([*hole, *board])
                ok = actual >= category
                if category == 1 and ok and not _hole_in_made_hand(hole, board):
                    ok = False  # a pair on the board is no pair in hand
                claim = f"has at least {CATEGORY_NAMES[category]}"
                why = f"{shown}; best: {CATEGORY_NAMES[actual]}"
                return _tag(seq, player, "poker_hand_claim", sentence, claim, ok, why)
    return None


# --- Werewolf -------------------------------------------------------------------------


def _werewolf(log: Log, spoilers: bool, names: Mapping[str, str] | None) -> list[dict[str, Any]]:
    from arena.analytics import werewolf

    tags = []
    texts = {seq: e.data["text"] for seq, e in log if e.type == MESSAGE}
    for claim in werewolf.analyze(log, spoilers, names)["claims"]:
        if claim.get("lie") is None:
            continue  # not known yet
        ok = not claim["lie"]
        sentence = texts.get(claim["seq"], "")
        true_role = claim.get("true_role")
        why = f"was {true_role}" if true_role else "the engine's role assignment"
        tags.append(
            _tag(claim["seq"], claim["player"], "role_claim", sentence,
                 f"is the {claim['role']}", ok, why)
        )  # fmt: skip
    return tags


# --- entry ----------------------------------------------------------------------------

CHECKS = {"liars_deck": "hands and plays", "poker": "hands", "werewolf": "role claims"}


def talk_checks(
    game: str, log: Log, spoilers: bool, names: Mapping[str, str] | None = None
) -> dict[str, Any]:
    """Every table-talk statement that could be read, with whether the engine's truth agrees.

    `log` holds (seq, event) pairs. Without `spoilers` only public events are read, and only
    Werewolf claims that a death has disproved are given; the other games need hidden cards.
    """
    if game not in CHECKS:
        return {
            "game": game,
            "available": False,
            "reason": "no talk check for this game",
            "tags": [],
        }
    if not spoilers:  # read public events only: a private message (pack chat) is no public talk
        log = [(seq, e) for seq, e in log if e.visible_to is None or e.type == "match_started"]
    if game == "werewolf":
        tags = _werewolf(log, spoilers, names)
        if not spoilers:
            tags = [t for t in tags if t["verdict"] == "false"]  # only what a death disproved
    elif not spoilers:
        return {
            "game": game,
            "available": False,
            "reason": "needs the hidden cards: shown with spoilers on",
            "tags": [],
        }
    else:
        tags = _liars_deck(log) if game == "liars_deck" else _poker(log)
    tags.sort(key=lambda t: t["seq"])
    summary: dict[str, dict[str, int]] = {}
    for tag in tags:
        row = summary.setdefault(tag["player"], {"checked": 0, "false": 0})
        row["checked"] += 1
        row["false"] += tag["verdict"] == "false"
    return {
        "game": game,
        "available": True,
        "checks": CHECKS[game],
        "heuristic": True,
        "tags": tags,
        "summary": summary,
    }
