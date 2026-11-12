"""The facts of a finished match, ready to be told: who did what, and why it mattered.

A digest is plain data. It names players by seat id and roles by role id; the words
(display names, styles, languages) come later in `arena.chronicle.compose`. A model narrator
can retell a chapter from its facts alone, and a fact checker can test the retelling against
them.

Like the rest of the chronicle it reads the log as a spectator does (hidden roles are in it)
and may be built only for a match that is over.
"""

import re
from typing import Any

from pydantic import BaseModel, Field

QUOTE_WORDS = 20  # a quote is at most this many words
MIN_CLAUSE = 8  # a cut at a clause boundary keeps at least this many words


class Fact(BaseModel):
    kind: str
    data: dict[str, Any] = Field(default_factory=dict)


class Section(BaseModel):
    """One chapter of the story: the prologue, a night, a day, or the epilogue."""

    kind: str  # "prologue" | "night" | "day" | "epilogue"
    number: int  # of the night or day; 0 for prologue and epilogue
    facts: list[Fact] = Field(default_factory=list)


class Digest(BaseModel):
    game: str
    seed: int
    seats: list[str]
    sections: list[Section]
    glance: list[Fact] = Field(default_factory=list)  # the "At a glance" box


SEAT = re.compile(r"\bp\d{1,2}\b", re.IGNORECASE)
SENTENCE = re.compile(r"(?<=[.!?])\s+")


def quote_of(text: str, seats: list[str], prefer_mention: bool = True) -> str | None:
    """A short verbatim quote from a public speech or a vote reason.

    The first sentence that points at another player (or the first sentence), cut at
    `QUOTE_WORDS` words with an ellipsis. None when the text names a seat that is not in the
    match (a model's slip), since such a quote could not be shown without a seat id.
    """
    text = " ".join(text.split())
    if not text:
        return None
    sentences = [s for s in SENTENCE.split(text) if s]
    chosen = sentences[0]
    if prefer_mention:
        for sentence in sentences:
            if SEAT.search(sentence):
                chosen = sentence
                break
    words = chosen.split()
    if len(words) > QUOTE_WORDS:
        cut = words[:QUOTE_WORDS]
        for i in range(len(cut) - 1, MIN_CLAUSE - 1, -1):  # end at a clause, not mid-phrase
            if cut[i].endswith((",", ";", ":")) or cut[i] in ("-", "—", "–"):
                cut = cut[: i + 1]
                break
        chosen = " ".join(cut).rstrip(",;:-—– ") + "…"
    known = {s.lower() for s in seats}
    if any(m.lower() not in known for m in SEAT.findall(chosen)):
        return None
    return chosen
