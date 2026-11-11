"""From the event log of a finished match to chapters of beats.

A beat is one thing worth telling, with the facts it needs (who, what, how many).
A chapter groups the beats of a round, a hand or a night. Nothing here is text:
`arena.chronicle.text` turns beats into words.

These functions read the log as a spectator sees it, so hidden cards and roles
are in the facts. They may only be called for a match that is over (the
`chronicle` entry point checks that): a story told during the match would give
the hidden information away.
"""

from collections.abc import Callable, Iterable
from typing import Any

from pydantic import BaseModel, Field

from arena.engine.types import Event, EventSource


class Beat(BaseModel):
    kind: str
    facts: dict[str, Any] = Field(default_factory=dict)


class Chapter(BaseModel):
    number: int
    kind: str  # "round", "hand" or "night"
    beats: list[Beat] = Field(default_factory=list)


def _game_events(events: Iterable[Event]) -> list[Event]:
    return [e for e in events if e.source is EventSource.GAME]


def _chapters(
    events: list[Event], opener: str, kind: str, handle: Callable[[Event, Chapter], None]
) -> list[Chapter]:
    """Cut `events` into chapters at every `opener` event and let `handle` add the beats."""
    chapters: list[Chapter] = []
    for event in events:
        if event.type == opener:
            chapters.append(Chapter(number=len(chapters) + 1, kind=kind))
        if chapters:
            handle(event, chapters[-1])
    return chapters


# --- Liar's Deck ------------------------------------------------------------------


def liars_deck(events: Iterable[Event]) -> list[Chapter]:
    state = {"card": "", "caller": "", "automatic": False}

    def handle(event: Event, chapter: Chapter) -> None:
        data = event.data
        match event.type:
            case "round_started":
                state["card"] = data["table_card"]
                chapter.beats.append(
                    Beat(
                        kind="ld_round",
                        facts={
                            "round": data["round"],
                            "card": data["table_card"],
                            "players": data["players"],
                        },
                    )
                )
            case "cards_played":
                chapter.beats.append(Beat(kind="ld_play", facts=dict(data)))
            case "liar_called":
                state["caller"], state["automatic"] = data["caller"], data["automatic"]
                kind = "ld_call_auto" if data["automatic"] else "ld_call"
                chapter.beats.append(
                    Beat(kind=kind, facts={"caller": data["caller"], "target": data["target"]})
                )
            case "cards_revealed":
                facts = {
                    "caller": state["caller"],
                    "target": data["player"],
                    "cards": data["cards"],
                    "card": state["card"],
                }
                kind = "ld_wrong" if data["honest"] else "ld_caught"
                chapter.beats.append(Beat(kind=kind, facts=facts))
            case "trigger_pulled":
                kind = "ld_bang" if data["live"] else "ld_click"
                chapter.beats.append(
                    Beat(kind=kind, facts={"player": data["player"], "pull": data["pull"]})
                )
            case "match_over":
                chapter.beats.append(Beat(kind="ld_win", facts={"winner": data["winner"]}))

    return _chapters(_game_events(events), "round_started", "round", handle)


# --- Poker ------------------------------------------------------------------------


def poker(events: Iterable[Event]) -> list[Chapter]:
    events = list(events)
    finished = next((e for e in events if e.type == "match_finished"), None)
    placements = finished.data["placements"] if finished else []
    leaders = [p["player"] for p in placements if p["rank"] == 1]

    def handle(event: Event, chapter: Chapter) -> None:
        data = event.data
        match event.type:
            case "hand_started":
                facts = {
                    "hand": data["hand"],
                    "button": data["button"],
                    "big_blind": data["big_blind"],
                }
                chapter.beats.append(Beat(kind="pk_hand", facts=facts))
            case "street_started" if data["street"] != "preflop":
                chapter.beats.append(
                    Beat(kind="pk_street", facts={"street": data["street"], "cards": data["cards"]})
                )
            case "bet_action":
                kinds = {"raise": "pk_raise", "all_in": "pk_allin", "fold": "pk_fold"}
                if data["kind"] in kinds:
                    facts = {"player": data["player"], "to": data["to"]}
                    chapter.beats.append(Beat(kind=kinds[data["kind"]], facts=facts))
            case "showdown":
                chapter.beats.append(Beat(kind="pk_showdown", facts={"hands": data["hands"]}))
            case "pot_awarded":
                winners = [p for p, amount in data["shares"].items() if amount > 0]
                chapter.beats.append(
                    Beat(kind="pk_award", facts={"winners": winners, "amount": data["amount"]})
                )
            case "players_eliminated":
                for player in data["players"]:
                    chapter.beats.append(Beat(kind="pk_out", facts={"player": player}))
            case "match_over" if data["winner"] is not None:
                chapter.beats.append(Beat(kind="pk_win", facts={"winner": data["winner"]}))
            case (
                "match_over"
            ):  # the hand limit ended it: the chip leaders are first in the standings
                chapter.beats.append(Beat(kind="pk_limit", facts={"leaders": leaders}))

    return _chapters(_game_events(events), "hand_started", "hand", handle)


# --- Werewolf ---------------------------------------------------------------------


def werewolf(events: Iterable[Event]) -> list[Chapter]:
    events = _game_events(events)
    cast = {e.data["player"]: e.data["role"] for e in events if e.type == "role_assigned"}

    def handle(event: Event, chapter: Chapter) -> None:
        data = event.data
        match event.type:
            case "night_started":
                if chapter.number == 1:
                    chapter.beats.append(Beat(kind="ww_cast", facts={"cast": cast}))
                chapter.beats.append(Beat(kind="ww_night", facts={"night": data["night"]}))
            case "morning_started" if not data["deaths"]:
                chapter.beats.append(Beat(kind="ww_dawn_quiet"))
            case "player_died":
                facts = {"player": data["player"], "role": data["role"], "cause": data["cause"]}
                chapter.beats.append(Beat(kind="ww_death", facts=facts))
            case "bear_growled":
                chapter.beats.append(Beat(kind="ww_growl"))
            case "vote_result":
                if data["executed"] is None:
                    chapter.beats.append(Beat(kind="ww_novote"))
                else:
                    facts = {
                        "executed": data["executed"],
                        "votes": data["counts"].get(data["executed"], 0),
                    }
                    chapter.beats.append(Beat(kind="ww_vote", facts=facts))
            case "hunter_shot":
                chapter.beats.append(
                    Beat(
                        kind="ww_hunter", facts={"player": data["player"], "target": data["target"]}
                    )
                )
            case "game_over":
                chapter.beats.append(Beat(kind="ww_end", facts={"outcome": data["winner"]}))

    return _chapters(events, "night_started", "night", handle)


BEATS: dict[str, Callable[[Iterable[Event]], list[Chapter]]] = {
    "liars_deck": liars_deck,
    "poker": poker,
    "werewolf": werewolf,
}
