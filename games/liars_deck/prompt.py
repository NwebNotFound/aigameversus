# ruff: noqa: E501  (lines of prose)
"""What a model reads about Liar's Deck: rules per prompt version and the situation summary.

Two versions exist so they can be compared (`prompt_version` in the match settings):

- `liars_deck-p1`: `rules.md` as it was, no summary.
- `liars_deck-p2`: `rules_v2.md` (rules, tools with example calls, how to play well) and a
  short summary above the situation, worked out from the observation only: it states
  nothing the player does not already see.

The functions are pure. The default is `DEFAULT_VERSION`.
"""

from collections.abc import Mapping
from importlib import resources
from math import comb
from typing import Any

from arena.agents.prompt import with_thought_in_the_call

VERSIONS = ("liars_deck-p1", "liars_deck-p1.1", "liars_deck-p2")
DEFAULT_VERSION = "liars_deck-p1"
_FILES = {"liars_deck-p1": "rules.md", "liars_deck-p2": "rules_v2.md"}

DECK = 20  # cards in the deck: 6 kings, 6 queens, 6 aces, 2 jokers
TRUE_CARDS = 8  # cards that count as the table card: 6 of that rank and 2 jokers


def version_of(settings: Mapping[str, Any] | None) -> str:
    """The prompt version a match uses: its `prompt_version` setting, else the default."""
    version = (settings or {}).get("prompt_version", DEFAULT_VERSION)
    if version not in VERSIONS:
        raise ValueError(f"Unknown prompt_version {version!r}; choose one of {list(VERSIONS)}")
    return version


def rules_text(version: str) -> str:
    if version == "liars_deck-p1.1":  # p1, with the thought where the system message asks for it
        return with_thought_in_the_call(rules_text("liars_deck-p1"))
    return resources.files("games.liars_deck").joinpath(_FILES[version]).read_text(encoding="utf-8")


def chance_all_true(cards: int, true_in_hand: int, hand_size: int) -> float:
    """The chance that `cards` unseen cards are all the table card or jokers.

    Treats them as drawn at random from the cards you do not hold. Real players do not draw
    at random (they choose what to play), so this is a baseline, not a verdict.
    """
    unseen = DECK - hand_size
    true_unseen = TRUE_CARDS - true_in_hand
    if cards > true_unseen or cards > unseen:
        return 0.0
    return comb(true_unseen, cards) / comb(unseen, cards)


def _is_true(card: str, table_card: str) -> bool:
    return card[0] == "J" or card == "DV" or card[0] == table_card[0].upper()


def _risk(player: Mapping[str, Any]) -> str:
    left = player["chambers"] - player["trigger_pulls"]
    return f"1/{left}" if left > 0 else "certain"


def situation_summary(observation: Mapping[str, Any]) -> str:
    """The turn at a glance, for the top of the prompt (version p2)."""
    you = observation["you"]
    table_card = observation["table_card"]
    hand = observation["hand"]
    mine = next(p for p in observation["players"] if p["id"] == you)
    true_cards = [c for c in hand if _is_true(c, table_card)]
    lines = [
        f"You are {you}. Round {observation['round']}, table card: {table_card} "
        f"({TRUE_CARDS} of the {DECK} cards count as a {table_card}: the six of that rank and the jokers).",
        f"Your hand ({len(hand)}): {' '.join(hand) or 'empty'}. "
        f"Cards that count as a {table_card}: {' '.join(true_cards) or 'none'} ({len(true_cards)}).",
        f"If you must shoot, the risk is {_risk(mine)} (you have pulled {mine['trigger_pulls']} time(s) so far).",
    ]
    last = observation["last_play"]
    if last and last["player"] != you:
        chance = chance_all_true(last["count"], len(true_cards), len(hand))
        lines.append(
            f"Last play: {last['player']} put down {last['count']} card(s) claiming {table_card}. "
            f"If those cards were drawn at random they would all be true with a chance of "
            f"{chance:.0%} (from your hand; players choose what they play, so judge the player too)."
        )
    elif last is None:
        lines.append("Nothing has been played yet this round: you cannot call, you must play.")
    others = [p for p in observation["players"] if p["id"] != you and p["alive"]]
    lines.append(
        "Others alive: "
        + "; ".join(f"{p['id']} {p['cards']} card(s), next shot {_risk(p)}" for p in others)
        + "."
    )
    return "\n".join(lines)
