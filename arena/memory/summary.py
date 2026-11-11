"""Long-term memory: a short summary of a match from one player's point of view.

The summary is written by a `Summarizer`. The default fills a template from the
facts that player saw and the final placements; no model is called. A model can
write it later through the same interface, without the memory store changing.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from arena.engine.types import Placement, PlayerId
from arena.memory.facts import Fact
from arena.memory.trust import TrustRules

NOTES_PER_PLAYER = 2  # in a summary; the relationship keeps more


@dataclass(frozen=True)
class MatchView:
    """Everything one player may know about a finished match, for its summary."""

    game_name: str
    me: PlayerId
    names: Mapping[PlayerId, str]  # every seat of the match, the player's own included
    placements: Sequence[Placement]
    facts: Sequence[Fact]  # only those whose observer is `me`
    game_id: str


class Summarizer(Protocol):
    def summarize(self, view: MatchView) -> str: ...


class TemplateSummarizer:
    """`Liar's Deck against Bob, Cara: 2nd of 3. Bob called me a liar in round 2 ...`"""

    def __init__(self, rules: TrustRules):
        self._rules = rules

    def summarize(self, view: MatchView) -> str:
        others = [seat for seat in view.names if seat != view.me]
        text = f"{view.game_name} against {', '.join(view.names[s] for s in others)}"
        rank = next((p.rank for p in view.placements if p.player == view.me), None)
        if rank is not None:
            text += f": I finished {_ordinal(rank)} of {len(view.placements)}."
        else:
            text += "."
        for seat in others:
            notes = [
                self._rules.facts[view.game_id][fact.kind].note.format(round=fact.round)
                for fact in view.facts
                if fact.about == seat
            ]
            if notes:
                text += f" {view.names[seat]} " + "; ".join(notes[:NOTES_PER_PLAYER]) + "."
        return text


def _ordinal(rank: int) -> str:
    suffix = "th" if 10 <= rank % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(rank % 10, "th")
    return f"{rank}{suffix}"
