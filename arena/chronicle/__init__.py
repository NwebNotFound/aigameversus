"""The chronicler: a finished match told as a story, chapter by chapter.

    chronicle = tell(events, style="epic", lang="en")
    print(to_markdown(chronicle))

The story is built from fixed templates, so it costs nothing and the same log
always gives the same text. `Narrator` is the seam for a model that retells a
chapter later; nothing here calls one.
"""

from collections.abc import Iterable, Mapping

from pydantic import BaseModel

from arena.chronicle.beats import BEATS, Beat, Chapter
from arena.chronicle.text import LANGS, STYLES, Narrator, TemplateNarrator
from arena.engine.types import Event, EventSource

__all__ = [
    "LANGS",
    "STYLES",
    "Beat",
    "Chapter",
    "ChapterText",
    "Chronicle",
    "ChronicleError",
    "Narrator",
    "TemplateNarrator",
    "chronicle_games",
    "to_markdown",
    "tell",
]


class ChronicleError(ValueError):
    """No chronicle: unknown game, style or language, or a match that is not over."""


class ChapterText(BaseModel):
    number: int
    title: str
    text: str


class Chronicle(BaseModel):
    game: str
    style: str
    lang: str
    title: str
    chapters: list[ChapterText]


def chronicle_games() -> list[str]:
    """The ids of the games that have a chronicle."""
    return sorted(BEATS)


def tell(
    events: Iterable[Event],
    *,
    style: str = "epic",
    lang: str = "en",
    names: Mapping[str, str] | None = None,
    narrator: Narrator | None = None,
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
    if game not in BEATS:
        raise ChronicleError(f"there is no chronicle for '{game}' (known: {', '.join(BEATS)})")
    if not any(e.source is EventSource.ENGINE and e.type == "match_finished" for e in events):
        raise ChronicleError(
            "the match is not over: the chronicle uses hidden information, "
            "so it exists only afterwards"
        )

    narrator = narrator or TemplateNarrator()
    names = names or {}
    chapters = [
        ChapterText(
            number=chapter.number,
            title=narrator.chapter_title(chapter.kind, chapter.number, style, lang),
            text=narrator.tell(chapter.beats, style, lang, names),
        )
        for chapter in BEATS[game](events)
    ]
    return Chronicle(
        game=game,
        style=style,
        lang=lang,
        title=narrator.title(game, style, lang),
        chapters=chapters,
    )


def to_markdown(chronicle: Chronicle) -> str:
    """The chronicle as a Markdown document: a title and one section per chapter."""
    parts = [f"# {chronicle.title}", ""]
    for chapter in chronicle.chapters:
        parts += [f"## {chapter.title}", "", chapter.text, ""]
    return "\n".join(parts)
