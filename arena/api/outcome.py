"""The one line that says how a match ended, made on the server for every list row.

It reads the record only (status, seats, placements), never the log, so a running match shows no
result and nothing hidden can leak: the winners of a finished match are public.
"""

from collections.abc import Mapping, Sequence
from typing import Any

from pydantic import BaseModel, Field

from arena.db.match_store import MatchRecord
from arena.transcript.common import display_names

STOPPED = {
    "failed": ("Failed", "Fehlgeschlagen"),
    "interrupted": ("Interrupted (a cap or a restart)", "Unterbrochen (Limit oder Neustart)"),
    "aborted": ("Aborted by a viewer", "Von einem Zuschauer abgebrochen"),
}


class Outcome(BaseModel):
    kind: str = Field(
        description="running, won, finished (no result kept) or stopped (failed, interrupted, "
        "aborted)"
    )
    winners: list[str] = Field(description="Seats with rank 1; empty unless the match finished")
    text: dict[str, str] = Field(description="The outcome in one line: en and de")


def names_of(record: MatchRecord) -> Mapping[str, str]:
    """Display names of the seats from the record alone (no query): a match recorded before
    seats were kept shows its seats as bots, which they were."""
    if record.seats:
        return display_names({p: (s.kind, s.name) for p, s in record.seats.items()})
    return display_names({p: ("bot", "") for p in record.players})


def _list(names: Sequence[str], lang: str) -> str:
    joiner = " und " if lang == "de" else " and "
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + joiner + names[-1]


def outcome_of(record: MatchRecord) -> Outcome:
    if record.status == "running":
        return Outcome(kind="running", winners=[], text={"en": "In progress", "de": "Läuft"})
    if record.status != "finished":
        en, de = STOPPED[record.status]
        return Outcome(kind="stopped", winners=[], text={"en": en, "de": de})
    if not record.placements:
        return Outcome(kind="finished", winners=[], text={"en": "Finished", "de": "Beendet"})
    names = names_of(record)
    winners = [p.player for p in record.placements if p.rank == 1]
    shown = [names.get(w, w) for w in winners]
    total = len(record.players)
    if len(winners) <= 3:
        text: dict[str, Any] = {
            "en": f"{_list(shown, 'en')} won",
            "de": f"{_list(shown, 'de')} {'gewann' if len(winners) == 1 else 'gewannen'}",
        }
    else:
        text = {
            "en": f"{len(winners)} of {total} players won",
            "de": f"{len(winners)} von {total} Spielern gewannen",
        }
    return Outcome(kind="won", winners=winners, text=text)
