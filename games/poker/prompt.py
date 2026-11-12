# ruff: noqa: E501  (lines of prose)
"""What a model reads about Poker: rules per prompt version and the situation summary.

- `poker-p1`: `rules.md` as it was, no summary.
- `poker-p2`: `rules_v2.md` and a short summary above the situation, worked out from the
  observation only: your cards, what you must pay, the pot odds, your stack in big blinds,
  and your chance to win against random hands. It states nothing the player does not see.

All functions are pure; the chance uses a random stream fixed by the situation.
"""

import random
from collections.abc import Mapping
from importlib import resources
from typing import Any

from arena.agents.prompt import with_thought_in_the_call
from games.poker.cards import FULL_DECK, Card
from games.poker.evaluator import HandCategory, best_hand

VERSIONS = ("poker-p1", "poker-p1.1", "poker-p2")
DEFAULT_VERSION = "poker-p1"
_FILES = {"poker-p1": "rules.md", "poker-p2": "rules_v2.md"}
SAMPLES = 400

RANK_NAMES = {14: "ace", 13: "king", 12: "queen", 11: "jack", 10: "ten"} | {
    n: str(n) for n in range(2, 10)
}
CATEGORY_WORDS = {
    HandCategory.HIGH_CARD: "high card",
    HandCategory.ONE_PAIR: "a pair",
    HandCategory.TWO_PAIR: "two pair",
    HandCategory.THREE_OF_A_KIND: "three of a kind",
    HandCategory.STRAIGHT: "a straight",
    HandCategory.FLUSH: "a flush",
    HandCategory.FULL_HOUSE: "a full house",
    HandCategory.FOUR_OF_A_KIND: "four of a kind",
    HandCategory.STRAIGHT_FLUSH: "a straight flush",
    HandCategory.ROYAL_FLUSH: "a royal flush",
}


def version_of(settings: Mapping[str, Any] | None) -> str:
    """The prompt version of a match: its `prompt_version` setting, else the default."""
    version = (settings or {}).get("prompt_version", DEFAULT_VERSION)
    if version not in VERSIONS:
        raise ValueError(f"Unknown prompt_version {version!r}; choose one of {list(VERSIONS)}")
    return version


def rules_text(version: str) -> str:
    if version == "poker-p1.1":  # p1, with the thought where the system message asks for it
        return with_thought_in_the_call(rules_text("poker-p1"))
    return resources.files("games.poker").joinpath(_FILES[version]).read_text(encoding="utf-8")


def starting_hand(cards: list[str]) -> str:
    """Two hole cards in words: "pocket kings", "ace-king suited", "seven-two offsuit"."""
    a, b = sorted((Card.parse(c) for c in cards), key=lambda c: -c.rank)
    if a.rank == b.rank:
        return f"a pocket pair of {RANK_NAMES[a.rank]}s"
    kind = "suited" if a.suit == b.suit else "offsuit"
    gap = a.rank - b.rank - 1
    shape = "connected" if gap == 0 else (f"{gap}-gap" if gap <= 2 else "far apart")
    return f"{RANK_NAMES[a.rank]}-{RANK_NAMES[b.rank]} {kind}, {shape}"


def made_hand(cards: list[str], board: list[str]) -> str:
    """The best hand so far in words, once five or more cards are known (else an empty string)."""
    known = [Card.parse(c) for c in [*cards, *board]]
    if len(known) < 5:
        return ""
    value = best_hand(known)
    words = CATEGORY_WORDS[value.category]
    if value.category is HandCategory.HIGH_CARD:
        return f"{words}: {RANK_NAMES[value.tiebreak[0]]}"
    if value.category is HandCategory.ONE_PAIR:
        return f"{words} of {RANK_NAMES[value.tiebreak[0]]}s"
    return words


def equity_vs_random(cards: list[str], board: list[str], opponents: int, seed: str) -> float:
    """Your chance to win (a tie counts half) against `opponents` hands dealt at random.

    A baseline: real opponents who bet usually hold more than random cards. Estimated from
    `SAMPLES` runouts with a random stream fixed by `seed`, so a situation always gives the same.
    """
    rng = random.Random(seed)
    mine = [Card.parse(c) for c in cards]
    shown = [Card.parse(c) for c in board]
    unseen = [c for c in FULL_DECK if c not in mine and c not in shown]
    wins = 0.0
    for _ in range(SAMPLES):
        draw = rng.sample(unseen, 5 - len(shown) + 2 * opponents)
        table = shown + draw[: 5 - len(shown)]
        best = best_hand(mine + table)
        rivals = [
            best_hand(draw[5 - len(shown) + 2 * i : 7 - len(shown) + 2 * i] + table)
            for i in range(opponents)
        ]
        top = max(rivals)
        wins += 1.0 if best > top else 0.5 if best == top else 0.0
    return wins / SAMPLES


def situation_summary(observation: Mapping[str, Any]) -> str:
    """Your turn at a glance, for the top of the prompt (version p2)."""
    you = observation["you"]
    cards, board = observation["your_cards"], observation["board"]
    players = observation["players"]
    mine = next(p for p in players if p["id"] == you)
    rivals = [p for p in players if p["id"] != you and p["in_hand"]]
    big_blind = observation["blinds"]["big"]
    street = observation["street"]
    pot, to_call = observation["pot"], observation["to_call"]

    lines = [
        f"You are {you}, {mine['position'] or 'out of the hand'}. Hand {observation['hand']}, {street}; "
        f"blinds {observation['blinds']['small']}/{big_blind}.",
        f"Your cards: {' '.join(cards)} ({starting_hand(cards)}). Board: {' '.join(board) or 'none yet'}"
        + (f". You have {made_hand(cards, board)}." if made_hand(cards, board) else "."),
        f"Your stack: {mine['stack']} chips = {mine['stack'] / big_blind:.1f} big blinds. Pot: {pot}.",
    ]
    if observation["your_turn"]:
        if to_call == 0:
            lines.append(
                "There is no bet to call: you may check or raise; folding would give up your chance for nothing."
            )
        else:
            price = to_call / (pot + to_call)
            lines.append(
                f"To call: {to_call} into a pot of {pot}: you need about {price:.0%} equity to break even."
            )
        if observation["min_raise_to"] is not None:
            lines.append(
                f"A raise must go to between {observation['min_raise_to']} and {observation['max_raise_to']} (total bet)."
            )
    if rivals:
        seed = f"{observation['hand']}/{street}/{' '.join(cards)}/{' '.join(board)}/{len(rivals)}"
        chance = equity_vs_random(cards, board, len(rivals), seed)
        lines.append(
            f"Against {len(rivals)} random hand(s) you win about {chance:.0%} of the time "
            "(real opponents who bet hold more than random cards, so discount it)."
        )
        lines.append(
            "In the hand: "
            + "; ".join(
                f"{p['id']} stack {p['stack']}, bet {p['bet']}"
                + (" (all in)" if p["all_in"] else "")
                for p in rivals
            )
            + "."
        )
    return "\n".join(lines)
