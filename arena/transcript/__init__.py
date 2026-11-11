"""The transcript: one readable play-by-play of a match, from its event log.

    lines = render_match(events, players=labels({"p1": "glm-flash", ...}), lang="de")
    print(to_text(lines))

This is the single source of readable text. The `arena` command, the API
(`GET /matches/{id}/transcript`), the live view, replays and exports all show these
lines, so they never disagree. Every event type of every game has a renderer; a test
fails when a plugin emits one without it. No line contains raw JSON.

Hidden information (hands, roles, private choices, thoughts, whispers) appears only with
`spoilers=True`. Public talk is always shown.
"""

from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from arena.engine.types import Event
from arena.transcript.common import KINDS, LANGS, Base, TranscriptLine, labels, names_from
from arena.transcript.liars_deck import LiarsDeck
from arena.transcript.poker import Poker
from arena.transcript.toy import Toy
from arena.transcript.werewolf import Werewolf

__all__ = [
    "KINDS",
    "LANGS",
    "RENDERERS",
    "Transcriber",
    "TranscriptError",
    "TranscriptLine",
    "from_export",
    "known_event_types",
    "labels",
    "render_event",
    "render_match",
    "to_markdown",
    "to_text",
]

RENDERERS: dict[str, type[Base]] = {
    "toy": Toy,
    "liars_deck": LiarsDeck,
    "poker": Poker,
    "werewolf": Werewolf,
}


class TranscriptError(ValueError):
    """The transcript cannot be made: unknown game or language, or a file that is not a match."""


def known_event_types(game: str) -> set[str]:
    """The event types the renderer of `game` can write, the engine's own included."""
    return RENDERERS[game].event_types()


class Transcriber:
    """Turns the events of one match into lines, in log order; it remembers round and street."""

    def __init__(
        self,
        game: str,
        players: Sequence[str] | Mapping[str, str] = (),
        lang: str = "en",
        spoilers: bool = False,
    ):
        if game not in RENDERERS:
            raise TranscriptError(f"no transcript for '{game}' (known: {', '.join(RENDERERS)})")
        if lang not in LANGS:
            raise TranscriptError(f"unknown language '{lang}' (known: {', '.join(LANGS)})")
        self._renderer = RENDERERS[game](lang, spoilers, names_from(players))

    def line(self, event: Event, seq: int | None = None) -> TranscriptLine | None:
        """The line for one event, or None when it is hidden without spoilers."""
        return self._renderer.line(event, seq)


def render_event(
    game: str,
    event: Event,
    players: Sequence[str] | Mapping[str, str] = (),
    lang: str = "en",
    spoilers: bool = False,
) -> TranscriptLine | None:
    """One event as a line. It knows nothing of earlier events: the table card, the street or
    the night number may be missing. Use `render_match` or `Transcriber` for a whole log."""
    return Transcriber(game, players, lang, spoilers).line(event)


def render_match(
    events: Iterable[Event],
    players: Sequence[str] | Mapping[str, str] | None = None,
    lang: str = "en",
    spoilers: bool = False,
    game: str | None = None,
) -> list[TranscriptLine]:
    """The whole log as lines. The game and the seats come from `match_started` if not given."""
    events = list(events)
    start = next((e for e in events if e.type == "match_started"), None)
    if game is None:
        if start is None:
            raise TranscriptError("the log does not start with match_started and no game was given")
        game = start.data["game"]
    if players is None:
        players = start.data["players"] if start else ()
    transcriber = Transcriber(game, players, lang, spoilers)
    lines = []
    for seq, event in enumerate(events):
        line = transcriber.line(event, seq)
        if line is not None:
            lines.append(line)
    return lines


def to_text(lines: Iterable[TranscriptLine], min_importance: int = 1, details: bool = True) -> str:
    """Plain text, one line each (a detail on an indented line below); headings get a blank line."""
    out: list[str] = []
    for line in lines:
        if line.importance < min_importance:
            continue
        if line.kind == "heading" and out:
            out.append("")
        out.append(line.text)
        if details and line.detail:
            out.append(f"    {line.detail}")
    return "\n".join(out) + "\n"


def to_markdown(
    lines: Iterable[TranscriptLine], min_importance: int = 1, details: bool = True
) -> str:
    """Markdown: headings as `##`, highlights in bold, thoughts and whispers in italics."""
    out: list[str] = []
    for line in lines:
        if line.importance < min_importance:
            continue
        if line.kind == "heading":
            out += ["", f"## {line.text}", ""]
            if details and line.detail:
                out += [f"*{line.detail}*", ""]
            continue
        text = f"**{line.text}**" if line.importance >= 3 else line.text
        if line.kind in ("thought", "whisper"):
            text = f"*{line.text}*"
        out.append(f"- {text}")
        if details and line.detail:
            out.append(f"  - {line.detail}")
    return "\n".join(out).lstrip("\n") + "\n"


def from_export(data: Mapping[str, Any]) -> tuple[str, list[Event], dict[str, str]]:
    """Game, events and display names from a saved match file.

    Both files the arena writes are understood: `arena run --save` (seats name their models)
    and the replay export of the web UI (`aigameversus-replay/1`).
    """
    try:
        if data.get("format") == "aigameversus-replay/1":
            match = data["match"]
            game, seats = match["game"], {p: p for p in match["players"]}
        else:
            game, seats = data["game"], dict(data["seats"])
        events = [Event(**event) for event in data["events"]]
    except (KeyError, TypeError, ValueError) as error:
        raise TranscriptError(f"not a saved match: {error}") from error
    return game, events, labels(seats) if data.get("seats") else seats
