"""What a player learned about the others in a match, as facts the server can count.

A fact is always from one player's point of view (the observer) and is found
only in the events that player could see: public events and events sent to
them. Thoughts, spectator-only events and other players' private events are
never read, so a fact cannot carry anyone else's private knowledge.

The trust each kind of fact is worth lives in `config/memory/trust.yaml`.
"""

from collections.abc import Callable, Iterable, Sequence

from pydantic import BaseModel, ConfigDict

from arena.engine.types import Event, EventSource, PlayerId
from games.werewolf.selection import load_roles


class Fact(BaseModel):
    model_config = ConfigDict(frozen=True)

    observer: PlayerId
    about: PlayerId
    kind: str
    round: int | None = None  # round, hand or day the fact happened in, for the note


def seen_by(events: Iterable[Event], player: PlayerId) -> list[Event]:
    """The game events `player` could see: public ones and those sent to them."""
    return [
        e
        for e in events
        if e.source is EventSource.GAME and (e.visible_to is None or player in e.visible_to)
    ]


def _liars_deck(me: PlayerId, events: Sequence[Event]) -> list[Fact]:
    facts = []
    round_no = None
    call: dict | None = None  # the call being resolved
    for event in events:
        data = event.data
        match event.type:
            case "round_started":
                round_no = data["round"]
            case "liar_called":
                call = None if data["automatic"] else data
            case "cards_revealed":
                liar, honest = data["player"], data["honest"]
                if not honest and liar != me:
                    facts.append(Fact(observer=me, about=liar, kind="caught_lying", round=round_no))
                if call is not None and honest:
                    if liar == me:
                        facts.append(
                            Fact(
                                observer=me,
                                about=call["caller"],
                                kind="accused_me_falsely",
                                round=round_no,
                            )
                        )
                    elif call["caller"] == me:
                        facts.append(
                            Fact(observer=me, about=liar, kind="honest_when_called", round=round_no)
                        )
                call = None
    return facts


def _poker(me: PlayerId, events: Sequence[Event]) -> list[Fact]:
    """A player who bet or raised in a hand and then lost its showdown bluffed (the stats' rule).

    A player who wins any pot of the hand, a side pot included, did not lose it.
    """
    facts = []
    hand_no = None
    in_hand: set[PlayerId] = set()
    aggressive: set[PlayerId] = set()
    shown: set[PlayerId] = set()
    won: set[PlayerId] = set()
    street_high = 0
    for event in events:
        data = event.data
        match event.type:
            case "hand_started":
                hand_no = data["hand"]
                in_hand, aggressive, shown, won = set(), set(), set(), set()
            case "street_started":
                street_high = 0
            case "blind_posted":
                in_hand.add(data["player"])
                street_high = max(street_high, data["amount"])
            case "bet_action":
                in_hand.add(data["player"])
                kind, to = data["kind"], data["to"]
                if kind == "raise" or (kind == "all_in" and to > street_high):
                    aggressive.add(data["player"])
                if kind not in ("fold", "check"):
                    street_high = max(street_high, to)
            case "showdown":
                shown = {hand["player"] for hand in data["hands"]}
            case "pot_awarded":
                won |= {player for player, chips in data["shares"].items() if chips > 0}
            case "hand_ended" if me in in_hand:
                for player in sorted((shown & aggressive) - won - {me}):
                    facts.append(
                        Fact(observer=me, about=player, kind="bluff_called", round=hand_no)
                    )
    return facts


def _werewolf(me: PlayerId, events: Sequence[Event]) -> list[Fact]:
    roles = load_roles()
    is_wolf = {role_id: role.hunts_with_wolves for role_id, role in roles.items()}
    facts = []
    day = None
    lovers: set[PlayerId] = set()
    exposed: set[PlayerId] = set()
    for event in events:
        data = event.data
        match event.type:
            case "day_started":
                day = data["day"]
            case "pack_revealed":
                for wolf in sorted(set(data["wolves"]) - {me}):
                    facts.append(Fact(observer=me, about=wolf, kind="packmate"))
            case "love_revealed":
                lovers = set(data["lovers"])
            case "seer_inspected" if data["player"] == me:
                if is_wolf.get(data["role"]) and data["target"] not in exposed:
                    exposed.add(data["target"])
                    facts.append(
                        Fact(observer=me, about=data["target"], kind="revealed_wolf", round=day)
                    )
            case "player_died":
                dead = data["player"]
                if dead != me and is_wolf.get(data["role"]) and dead not in exposed:
                    exposed.add(dead)
                    facts.append(Fact(observer=me, about=dead, kind="revealed_wolf", round=day))
            case "vote_cast" if data["target"] == me and data["player"] != me:
                voter = data["player"]
                kind = "lover_voted_against_me" if {me, voter} <= lovers else "voted_against_me"
                facts.append(Fact(observer=me, about=voter, kind=kind, round=day))
    return facts


EXTRACTORS: dict[str, Callable[[PlayerId, Sequence[Event]], list[Fact]]] = {
    "liars_deck": _liars_deck,
    "poker": _poker,
    "werewolf": _werewolf,
}

# Every kind a game's extractor can produce; trust.yaml must give each one a value.
KINDS: dict[str, set[str]] = {
    "liars_deck": {"caught_lying", "accused_me_falsely", "honest_when_called"},
    "poker": {"bluff_called"},
    "werewolf": {"packmate", "revealed_wolf", "voted_against_me", "lover_voted_against_me"},
}


def match_facts(game_id: str, events: Iterable[Event], players: Sequence[PlayerId]) -> list[Fact]:
    """Every fact of a match, each read only from what its observer could see.

    A game without an extractor (High Card, or a game that has none yet) gives none.
    """
    extract = EXTRACTORS.get(game_id)
    if extract is None:
        return []
    events = list(events)
    seated = set(players)
    return [
        fact
        for player in players
        for fact in extract(player, seen_by(events, player))
        if fact.about in seated and fact.about != fact.observer
    ]
