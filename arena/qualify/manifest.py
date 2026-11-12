"""The core cases of each game (research/QUALIFY.md "Core pre-flight"), versioned.

Each case names the turn it needs (a predicate on the probed seat's request), which of the
engine's tools the model is offered there, and whether the thought is required. Speech
(table talk) is never offered: a qualification checks moves, and speech is never a move.

A game without a manifest here cannot be qualified yet; that is said, never guessed.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from arena.engine.types import ToolSpec, TurnRequest

MANIFEST_VERSION = "core-1"
SPEECH = {"table_talk", "speak"}


def _names(request: TurnRequest) -> set[str]:
    return {tool.name for tool in request.tools}


def _only(*names: str) -> Callable[[list[ToolSpec]], list[ToolSpec]]:
    return lambda tools: [tool for tool in tools if tool.name in names]


def _moves(tools: list[ToolSpec]) -> list[ToolSpec]:
    return [tool for tool in tools if tool.name not in SPEECH]


@dataclass(frozen=True)
class Case:
    id: str  # A..F of the protocol
    check: str  # the predicate in words, stored with the result
    fits: Callable[[TurnRequest], bool]
    offer: Callable[[list[ToolSpec]], list[ToolSpec]] = _moves
    longest: bool = False  # case C: the turn with the most history of the search match
    thought_required: bool = False


@dataclass(frozen=True)
class GameManifest:
    game: str
    players: list[str]
    settings: dict[str, Any] = field(default_factory=dict)
    player: str = "p1"
    cases: tuple[Case, ...] = ()
    not_applicable: dict[str, str] = field(default_factory=dict)  # case -> schema evidence


FOUR = ["p1", "p2", "p3", "p4"]

MANIFESTS: dict[str, GameManifest] = {
    "liars_deck": GameManifest(
        game="liars_deck",
        players=FOUR,
        cases=(
            Case(
                "A",
                "play_cards alone offered: legal ids of own cards; a short thought",
                lambda r: "play_cards" in _names(r) and "call_liar" not in _names(r),
                _only("play_cards"),
                thought_required=True,
            ),
            Case(
                "B",
                "after an opponent's play: play own cards or call liar, by the rules",
                lambda r: {"play_cards", "call_liar"} <= _names(r),
            ),
            Case(
                "C",
                "the turn with the most history of the search match, every move offered",
                lambda r: bool(_names(r) - SPEECH),
                longest=True,
            ),
            Case(
                "D",
                "call_liar alone offered: a game tool with no required arguments",
                lambda r: "call_liar" in _names(r),
                _only("call_liar"),
            ),
        ),
    ),
    "poker": GameManifest(
        game="poker",
        players=FOUR,
        cases=(
            Case(
                "A",
                "check or call, or fold, offered: one legal betting move; a short thought",
                lambda r: bool({"check", "call"} & _names(r)),
                _only("check", "call", "fold"),
                thought_required=True,
            ),
            Case(
                "B",
                "raise alone offered: an amount inside the offered bounds",
                lambda r: "raise" in _names(r),
                _only("raise"),
            ),
            Case(
                "C",
                "the turn with the most history of the search match, every move offered",
                lambda r: bool(_names(r) - SPEECH),
                longest=True,
            ),
            Case(
                "D",
                "check alone offered: a game tool with no arguments",
                lambda r: "check" in _names(r),
                _only("check"),
            ),
        ),
    ),
    # The toy game: for the arena's own tests of the runner.
    "toy": GameManifest(
        game="toy",
        players=["p1", "p2"],
        cases=(
            Case(
                "A",
                "play_card: a card from the own hand; a short thought",
                lambda r: "play_card" in _names(r),
                thought_required=True,
            ),
            Case(
                "C",
                "the turn with the most history of the search match",
                lambda r: "play_card" in _names(r),
                longest=True,
            ),
        ),
        not_applicable={"D": "play_card is the only tool and requires `card`"},
    ),
}
