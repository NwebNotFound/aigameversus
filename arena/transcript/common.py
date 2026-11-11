# ruff: noqa: E501  (lines of prose)
"""What every game's transcript shares: the line type, names, and the engine's own events.

A transcript is the match told as a play-by-play, one readable line per event, in
English or German. It is the one source of readable text: the CLI, the API, the live
view, replays and exports all show these lines. Nothing here prints raw JSON.

`kind` says what a line is, for UIs that draw bubbles or fold lines:

- `heading`: a round, hand, night or day begins.
- `action`: a player does something in the open (plays, bets, votes, shoots).
- `speech`: public talk; `whisper`: private talk (wolves, lovers); `thought`: a private thought.
- `reveal`: hidden information comes out (cards shown, a role told, a vote tally).
- `result`: a pot, a death, an elimination, the end of the match.
- `narration`: the narrator's own words (Werewolf).
- `info`: bookkeeping (deals, turn hand-overs, accepted actions, engine notes).

`importance`: 1 bookkeeping (fold it), 2 normal, 3 highlight.
"""

from collections.abc import Mapping, Sequence
from typing import Any

from pydantic import BaseModel

from arena.engine.types import MESSAGE, Event, EventSource

LANGS = ("en", "de")

# Settings anyone may read. The role mix (`template`, `roles`) is hidden information in Werewolf
# unless `roles_public` is on, so it is not in the list.
PUBLIC_SETTINGS = {
    "language",
    "variant",
    "duplicate",
    "hand_size",
    "captain",
    "roles_public",
    "prompt_version",
}


def public_settings(settings: Mapping[str, Any]) -> dict[str, Any]:
    """The settings of a match as a reader without spoilers may see them."""
    keep = set(PUBLIC_SETTINGS)
    if settings.get("roles_public"):
        keep |= {"template", "roles"}
    return {k: v for k, v in settings.items() if k in keep}


# Events whose audience is "spectators only" in the log but that tell nothing secret.
ALWAYS_SHOWN = {"match_started", "match_paused", "match_resumed", "turn_limit_reached"}

KINDS = (
    "heading",
    "action",
    "speech",
    "whisper",
    "thought",
    "reveal",
    "result",
    "narration",
    "info",
)


class TranscriptLine(BaseModel):
    seq: int | None = None
    kind: str
    actor: str | None = None  # the seat id of whoever acts or speaks, if one does
    text: str
    detail: str | None = None  # a second, less important sentence
    importance: int = 2
    raw: dict[str, Any]  # the event as stored, for the "raw" toggle


class Words:
    """Names and small phrases of one language, shared by the games."""

    def __init__(self, lang: str, names: Mapping[str, str]):
        self.lang = lang
        self.names = names

    def who(self, player: Any) -> str:
        """A player as "Name (model)", or the seat id when nobody gave a name."""
        if player is None:
            return "niemand" if self.lang == "de" else "nobody"
        return self.names.get(player, str(player))

    def many(self, players: Sequence[Any]) -> str:
        named = [self.who(p) for p in players]
        if len(named) <= 1:
            return "".join(named)
        word = " und " if self.lang == "de" else " and "
        return ", ".join(named[:-1]) + word + named[-1]

    def pick(self, en: str, de: str) -> str:
        return de if self.lang == "de" else en

    def number(self, count: int, en_one: str, en_many: str, de_one: str, de_many: str) -> str:
        """`count` with a noun: 1 card, 2 cards."""
        one, many = (de_one, de_many) if self.lang == "de" else (en_one, en_many)
        return f"{count} {one if count == 1 else many}"


def names_from(players: Sequence[str] | Mapping[str, str]) -> dict[str, str]:
    """The names to show: a mapping seat to display name, or just the seat ids."""
    if isinstance(players, Mapping):
        return dict(players)
    return {p: p for p in players}


def display_names(seats: Mapping[str, tuple[str, str]]) -> dict[str, str]:
    """The name every reader sees for each seat, unique within the match.

    `seats` maps a seat id to (kind, name): a model is shown by its short name ("gpt-luna"),
    numbered "gpt-luna #1", "gpt-luna #2" when the same model sits more than once; a bot is
    "Bot 3" with the number of its seat. The seat id itself is never the name.
    """
    count: dict[str, int] = {}
    for kind, name in seats.values():
        if kind != "bot":
            count[name] = count.get(name, 0) + 1
    seen: dict[str, int] = {}
    shown = {}
    for number, (seat, (kind, name)) in enumerate(seats.items(), start=1):
        if kind == "bot":
            digits = "".join(c for c in str(seat) if c.isdigit())
            shown[seat] = f"Bot {digits or number}"
        elif count[name] > 1:
            seen[name] = seen.get(name, 0) + 1
            shown[seat] = f"{name} #{seen[name]}"
        else:
            shown[seat] = name
    return shown


def labels(seats: Mapping[str, str]) -> dict[str, str]:
    """Display names from a mapping seat to model name (a saved `arena run --models` match)."""
    return display_names({seat: ("model", model) for seat, model in seats.items()})


class Base:
    """One game's renderer: `line(event)` turns one event into a line, or None to leave it out.

    It keeps what it has learned from earlier events (the table card, the street), so
    lines come out in log order. Subclasses set `GAME` and add `handle_<type>` methods; the
    ones in this class cover what the engine itself records.
    """

    GAME = ""

    def __init__(self, lang: str, spoilers: bool, names: Mapping[str, str]):
        if lang not in LANGS:
            raise ValueError(f"unknown language '{lang}' (known: {', '.join(LANGS)})")
        self.w = Words(lang, names)
        self.spoilers = spoilers

    # -- entry -------------------------------------------------------------------

    def line(self, event: Event, seq: int | None = None) -> TranscriptLine | None:
        # What only some players or only spectators could see is shown with spoilers on.
        if event.visible_to is not None and not self.spoilers and event.type not in ALWAYS_SHOWN:
            self.learn(event)
            return None
        handler = getattr(self, f"handle_{event.type}", None)
        if handler is None:
            raise KeyError(f"{self.GAME or 'engine'}: no renderer for event '{event.type}'")
        built = handler(event)
        if built is None:
            return None
        kind, actor, text, detail, importance = built
        raw = event.model_dump(mode="json")
        if not self.spoilers:
            # The seed would give every hidden draw away, so it is not in the raw event either.
            raw["data"] = {k: v for k, v in raw["data"].items() if k != "seed"}
            if event.type == "match_started":
                raw["data"]["settings"] = public_settings(raw["data"].get("settings") or {})
        return TranscriptLine(
            seq=seq,
            kind=kind,
            actor=actor,
            text=text,
            detail=detail,
            importance=importance,
            raw=raw,
        )

    def learn(self, event: Event) -> None:
        """Remember what a hidden event tells the later lines, without writing it out."""

    @classmethod
    def event_types(cls) -> set[str]:
        return {name.removeprefix("handle_") for name in dir(cls) if name.startswith("handle_")}

    # -- helpers -----------------------------------------------------------------

    def out(
        self,
        kind: str,
        text: str,
        *,
        actor: str | None = None,
        detail: str | None = None,
        importance: int = 2,
    ) -> tuple[str, str | None, str, str | None, int]:
        return kind, actor, text, detail, importance

    def tool(self, data: Mapping[str, Any]) -> str:
        """An action as words: `play_cards: card ids K1, Q3`. Arguments are shown as key: value."""
        arguments = data.get("arguments") or {}
        shown = ", ".join(f"{k.replace('_', ' ')}: {self._value(v)}" for k, v in arguments.items())
        name = str(data.get("tool", "")).replace("_", " ")
        return f"{name} ({shown})" if shown else name

    def _value(self, value: Any) -> str:
        if isinstance(value, (list, tuple)):
            return ", ".join(self._value(v) for v in value)
        if isinstance(value, Mapping):
            return ", ".join(f"{k}: {self._value(v)}" for k, v in value.items())
        return self.w.who(value) if value in self.w.names else str(value)

    # -- the engine's own events (every game) ---------------------------------------

    def handle_match_started(self, event: Event):
        data = event.data
        players = self.w.many(data["players"])
        text = self.w.pick(f"Match started: {players}", f"Das Spiel beginnt: {players}")
        if self.spoilers:  # the seed would give every hidden draw away
            seed = self.w.pick(f"seed {data['seed']}", f"Seed {data['seed']}")
            text = f"{text} ({seed})"
        return self.out("heading", text, importance=2)

    def handle_thought(self, event: Event):
        who = self.w.who(event.data["player"])
        label = self.w.pick("thinks", "denkt")
        return self.out(
            "thought",
            f"{who} {label}: {event.data['text']}",
            actor=event.data["player"],
            importance=2,
        )

    def handle_action_accepted(self, event: Event):
        who = self.w.who(event.data["player"])
        text = self.w.pick(
            f"{who} chooses {self.tool(event.data)}", f"{who} wählt {self.tool(event.data)}"
        )
        return self.out("info", text, actor=event.data["player"], importance=1)

    def handle_action_rejected(self, event: Event):
        who = self.w.who(event.data["player"])
        text = self.w.pick(
            f"{who}'s move was refused: {event.data['error']}",
            f"Der Zug von {who} wurde abgelehnt: {event.data['error']}",
        )
        return self.out(
            "info", text, actor=event.data["player"], detail=self.tool(event.data), importance=2
        )

    def handle_action_fallback(self, event: Event):
        who = self.w.who(event.data["player"])
        reason = event.data.get("reason", "")
        text = self.w.pick(
            f"No usable move from {who} ({reason}): a random move is played",
            f"Kein brauchbarer Zug von {who} ({reason}): ein Zufallszug wird gespielt",
        )
        return self.out(
            "info", text, actor=event.data["player"], detail=self.tool(event.data), importance=2
        )

    def handle_decision(self, event: Event):
        """What a move took: bookkeeping for statistics, shown only at the finest detail."""
        data = event.data
        parts = []
        if data.get("latency_ms") is not None:
            parts.append(f"{data['latency_ms'] / 1000:.1f} s")
        if data.get("tokens_in") is not None or data.get("tokens_out") is not None:
            parts.append(
                self.w.pick(
                    f"{data.get('tokens_in') or 0} tokens in, {data.get('tokens_out') or 0} out",
                    f"{data.get('tokens_in') or 0} Tokens rein, {data.get('tokens_out') or 0} raus",
                )
            )
        if data.get("retries"):
            parts.append(
                self.w.pick(f"{data['retries']} retries", f"{data['retries']} Wiederholungen")
            )
        who = self.w.who(data["player"])
        text = self.w.pick(f"{who}'s move", f"Zug von {who}") + (
            ": " + ", ".join(parts) if parts else ""
        )
        return self.out("info", text, actor=data["player"], importance=1)

    def handle_agent_failed(self, event: Event):
        who = self.w.who(event.data["player"])
        text = self.w.pick(
            f"{who} drops out of the game as a player ({event.data.get('error', 'error')}); random moves from now on",
            f"{who} fällt als Spieler aus ({event.data.get('error', 'Fehler')}); ab jetzt Zufallszüge",
        )
        return self.out("info", text, actor=event.data["player"], importance=2)

    def handle_match_paused(self, event: Event):
        reason = event.data.get("reason", "")
        return self.out(
            "info",
            self.w.pick(f"The match is paused ({reason})", f"Das Spiel ist angehalten ({reason})"),
            importance=2,
        )

    def handle_match_resumed(self, event: Event):
        return self.out(
            "info", self.w.pick("The match goes on", "Das Spiel geht weiter"), importance=2
        )

    def handle_turn_limit_reached(self, event: Event):
        return self.out(
            "result",
            self.w.pick(
                f"The match was stopped after {event.data['max_turns']} turns (turn limit)",
                f"Das Spiel wurde nach {event.data['max_turns']} Zügen abgebrochen (Zuglimit)",
            ),
            importance=3,
        )

    def handle_match_finished(self, event: Event):
        ranking = sorted(event.data["placements"], key=lambda p: p["rank"])
        parts = [f"{p['rank']}. {self.w.who(p['player'])}" for p in ranking]
        label = self.w.pick("Result", "Ergebnis")
        return self.out("result", f"{label}: " + "  ".join(parts), importance=3)

    def handle_message(self, event: Event):
        """Talk: public talk always, private talk (wolves, lovers) only with spoilers."""
        who = self.w.who(event.data["player"])
        if event.visible_to is None:
            return self.out("speech", f'{who}: "{event.data["text"]}"', actor=event.data["player"])
        label = self.w.pick("whispers", "flüstert")
        return self.out(
            "whisper", f'{who} {label}: "{event.data["text"]}"', actor=event.data["player"]
        )


def is_engine(event: Event) -> bool:
    return event.source is EventSource.ENGINE


assert MESSAGE == "message"  # handle_message is the renderer of the shared talk event
