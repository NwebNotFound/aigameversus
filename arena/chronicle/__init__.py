"""The chronicler: a finished match told as a story, chapter by chapter.

    chronicle = tell(events, style="epic", lang="en")
    print(to_markdown(chronicle))

Each game has a digest of the facts of its match (`<game>.py`) and templates in four
styles and two languages (`templates/`, worded by `compose`), so the story costs nothing
and the same log always gives the same text. `arena.chronicle.ai` has a model retell it.
"""

from collections.abc import Iterable, Mapping
from typing import Any

from pydantic import BaseModel, Field

from arena.chronicle import civ, compose, liars_deck, poker, werewolf
from arena.chronicle.text import LANGS, STYLES
from arena.engine.types import Event, EventSource

__all__ = [
    "LANGS",
    "STYLES",
    "ChapterText",
    "Chronicle",
    "GlanceItem",
    "ChronicleError",
    "chronicle_games",
    "to_markdown",
    "tell",
]


# The digest of each game that has a chronicle.
GAMES = {
    "werewolf": werewolf.build,
    "liars_deck": liars_deck.build,
    "poker": poker.build,
    "civ": civ.build,
}


class ChronicleError(ValueError):
    """No chronicle: unknown game, style or language, or a match that is not over."""


class ChapterText(BaseModel):
    number: int
    title: str
    text: str
    kind: str = "round"  # prologue and epilogue; night or day, round, level, age by game
    seq: int | None = None  # where in the whole log the chapter begins


class GlanceItem(BaseModel):
    label: str
    value: str


class Chronicle(BaseModel):
    game: str
    style: str
    lang: str
    title: str
    chapters: list[ChapterText]
    glance_title: str = ""
    glance: list[GlanceItem] = Field(default_factory=list)  # the "At a glance" box
    key_moments: list[dict[str, Any]] = Field(default_factory=list)  # {seq, kind, players, ...}


def chronicle_games() -> list[str]:
    """The ids of the games that have a chronicle."""
    return sorted(GAMES)


def tell(
    events: Iterable[Event],
    *,
    style: str = "epic",
    lang: str = "en",
    names: Mapping[str, str] | None = None,
    cost_micro_eur: int | None = None,
) -> Chronicle:
    """The chronicle of a finished match, from its whole event log.

    `names` maps a player id to the name used in the text (for example a model's
    name); a player without an entry is called by its id.

    Spectator information only: the story names hidden cards and roles, so it is
    told only once the match is over. A log without `match_finished` is refused.
    """
    events = list(events)
    if style not in STYLES:
        raise ChronicleError(f"unknown style '{style}' (known: {', '.join(STYLES)})")
    if lang not in LANGS:
        raise ChronicleError(f"unknown language '{lang}' (known: {', '.join(LANGS)})")
    start = next((e for e in events if e.type == "match_started"), None)
    if start is None:
        raise ChronicleError("the log does not start with match_started")
    game = start.data["game"]
    if game not in chronicle_games():
        known = ", ".join(chronicle_games())
        raise ChronicleError(f"there is no chronicle for '{game}' (known: {known})")
    if not any(e.source is EventSource.ENGINE and e.type == "match_finished" for e in events):
        raise ChronicleError(
            "the match is not over: the chronicle uses hidden information, "
            "so it exists only afterwards"
        )

    names = names or {}
    digest = GAMES[game](events, names)
    teller = compose.Teller(digest, style, lang, names)
    return Chronicle(
        game=game,
        style=style,
        lang=lang,
        title=teller.tpl["title"],
        chapters=[ChapterText(**c) for c in compose.chapters(teller)],
        glance_title=teller.tpl["glance_title"],
        glance=[GlanceItem(**g) for g in compose.glance(teller, cost_micro_eur)],
        key_moments=compose.key_moments(digest),
    )


def to_markdown(chronicle: Chronicle) -> str:
    """The chronicle as a Markdown document: a title, the glance box, one section per chapter."""
    parts = [f"# {chronicle.title}", ""]
    if chronicle.glance:
        parts += [f"## {chronicle.glance_title}", ""]
        parts += [f"- **{item.label}:** {item.value}" for item in chronicle.glance]
        parts.append("")
    for chapter in chronicle.chapters:
        parts += [f"## {chapter.title}", "", chapter.text, ""]
    return "\n".join(parts)
