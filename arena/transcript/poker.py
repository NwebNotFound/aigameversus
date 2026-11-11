# ruff: noqa: E501  (lines of prose)
"""Poker as a play-by-play."""

from typing import Any

from arena.engine.types import Event
from arena.transcript.common import Base
from games.poker.cards import Card
from games.poker.evaluator import HandCategory, best_hand

SUITS = {"c": "♣", "d": "♦", "h": "♥", "s": "♠"}

# Singular name of a rank, its plural, and the German article for "ein Paar ..." forms.
RANKS = {
    "en": {
        14: ("ace", "aces"), 13: ("king", "kings"), 12: ("queen", "queens"), 11: ("jack", "jacks"),
        10: ("ten", "tens"), 9: ("nine", "nines"), 8: ("eight", "eights"), 7: ("seven", "sevens"),
        6: ("six", "sixes"), 5: ("five", "fives"), 4: ("four", "fours"), 3: ("three", "threes"),
        2: ("deuce", "deuces"),
    },
    "de": {
        14: ("Ass", "Asse"), 13: ("König", "Könige"), 12: ("Dame", "Damen"), 11: ("Bube", "Buben"),
        10: ("Zehn", "Zehner"), 9: ("Neun", "Neuner"), 8: ("Acht", "Achter"), 7: ("Sieben", "Siebener"),
        6: ("Sechs", "Sechser"), 5: ("Fünf", "Fünfer"), 4: ("Vier", "Vierer"), 3: ("Drei", "Dreier"),
        2: ("Zwei", "Zweier"),
    },
}  # fmt: skip
STREET = {
    "en": {"preflop": "Pre-flop", "flop": "Flop", "turn": "Turn", "river": "River"},
    "de": {"preflop": "Pre-Flop", "flop": "Flop", "turn": "Turn", "river": "River"},
}


def show(cards: list[str]) -> str:
    """Cards as symbols: ["Kh", "8c"] becomes "K♥ 8♣"."""
    return " ".join(f"{c[0].replace('T', '10')}{SUITS[c[1]]}" for c in cards)


class Poker(Base):
    GAME = "poker"

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.street = "preflop"
        self.board: list[str] = []
        self.shown: dict[str, str] = {}  # player to the words for their hand, at a showdown
        self.hole: dict[str, list[str]] = {}

    # -- words ---------------------------------------------------------------------

    def street_name(self) -> str:
        return STREET[self.w.lang][self.street]

    def hand_words(self, hole: list[str], board: list[str]) -> str:
        """The best hand of a player as words: "a pair of kings"."""
        value = best_hand([*map(Card.parse, hole), *map(Card.parse, board)])
        lang = self.w.lang
        names = RANKS[lang]
        t = value.tiebreak
        category = value.category
        if category is HandCategory.HIGH_CARD:
            return self.w.pick(f"{names[t[0]][0]} high", f"{names[t[0]][0]} hoch")
        if category is HandCategory.ONE_PAIR:
            return self.w.pick(f"a pair of {names[t[0]][1]}", f"ein Paar {names[t[0]][1]}")
        if category is HandCategory.TWO_PAIR:
            both = self.w.pick(" and ", " und ").join(names[r][1] for r in t[:2])
            return self.w.pick(f"two pair, {both}", f"zwei Paare, {both}")
        if category is HandCategory.THREE_OF_A_KIND:
            return self.w.pick(f"three {names[t[0]][1]}", f"Drilling {names[t[0]][1]}")
        if category is HandCategory.STRAIGHT:
            return self.w.pick(
                f"a straight to the {names[t[0]][0]}", f"eine Straße bis {names[t[0]][0]}"
            )
        if category is HandCategory.FLUSH:
            return self.w.pick(
                f"a flush, {names[t[0]][0]} high", f"ein Flush, {names[t[0]][0]} hoch"
            )
        if category is HandCategory.FULL_HOUSE:
            return self.w.pick(
                f"a full house, {names[t[0]][1]} over {names[t[1]][1]}",
                f"ein Full House, {names[t[0]][1]} über {names[t[1]][1]}",
            )
        if category is HandCategory.FOUR_OF_A_KIND:
            return self.w.pick(f"four {names[t[0]][1]}", f"Vierling {names[t[0]][1]}")
        if category is HandCategory.STRAIGHT_FLUSH:
            return self.w.pick(
                f"a straight flush to the {names[t[0]][0]}",
                f"ein Straight Flush bis {names[t[0]][0]}",
            )
        return self.w.pick("a royal flush", "ein Royal Flush")

    # -- events --------------------------------------------------------------------

    def handle_hand_started(self, event: Event):
        data = event.data
        self.street, self.board, self.shown, self.hole = "preflop", [], {}, {}
        text = self.w.pick(
            f"Hand {data['hand']}: {self.w.who(data['button'])} has the button, blinds {data['small_blind']}/{data['big_blind']}",
            f"Hand {data['hand']}: {self.w.who(data['button'])} hat den Button, Blinds {data['small_blind']}/{data['big_blind']}",
        )
        detail = self.w.pick(
            f"In the hand: {self.w.many(data['players'])}",
            f"In der Hand: {self.w.many(data['players'])}",
        )
        return self.out("heading", text, detail=detail, importance=2)

    def handle_deck_shuffled(self, event: Event):
        return self.out(
            "info", self.w.pick("The deck is shuffled", "Das Deck wird gemischt"), importance=1
        )

    def handle_hole_dealt(self, event: Event):
        data = event.data
        self.hole[data["player"]] = data["cards"]
        who = self.w.who(data["player"])
        text = self.w.pick(
            f"{who} is dealt {show(data['cards'])}", f"{who} bekommt {show(data['cards'])}"
        )
        return self.out("info", text, actor=data["player"], importance=1)

    def learn(self, event: Event) -> None:
        if event.type == "hole_dealt":
            self.hole[event.data["player"]] = event.data["cards"]

    def handle_blind_posted(self, event: Event):
        data = event.data
        who = self.w.who(data["player"])
        big = data["kind"] == "big"
        text = self.w.pick(
            f"{who} posts the {'big' if big else 'small'} blind ({data['amount']})",
            f"{who} setzt den {'großen' if big else 'kleinen'} Blind ({data['amount']})",
        )
        return self.out("info", text, actor=data["player"], importance=1)

    def handle_street_started(self, event: Event):
        data = event.data
        self.street = data["street"]
        self.board += data["cards"]
        if self.street == "preflop":
            first = self.w.who(data["order"][0]) if data["order"] else ""
            return self.out(
                "heading",
                self.w.pick(f"Pre-flop: {first} acts first", f"Pre-Flop: {first} beginnt"),
                importance=2,
            )
        label = self.street_name()
        text = f"{label}: {show(data['cards'])}"
        if self.street != "flop":
            text += f" ({self.w.pick('board', 'Board')}: {show(self.board)})"
        return self.out("reveal", text, importance=2)

    def handle_bet_action(self, event: Event):
        data = event.data
        who = self.w.who(data["player"])
        street = STREET[self.w.lang][data["street"]]
        kind = data["kind"]
        if kind == "fold":
            verb = self.w.pick("folds", "passt")
        elif kind == "check":
            verb = self.w.pick("checks", "checkt")
        elif kind == "call":
            verb = self.w.pick(f"calls {data['added']}", f"geht mit ({data['added']})")
        elif kind == "raise":
            verb = self.w.pick(f"raises to {data['to']}", f"erhöht auf {data['to']}")
        else:
            verb = self.w.pick(f"goes all-in ({data['to']})", f"geht All-in ({data['to']})")
        importance = 3 if kind == "all_in" else 2
        return self.out(
            "action", f"{street}: {who} {verb}", actor=data["player"], importance=importance
        )

    def handle_showdown(self, event: Event):
        parts = []
        for entry in event.data["hands"]:
            words = self.hand_words(entry["cards"], self.board)
            self.shown[entry["player"]] = words
            who = self.w.who(entry["player"])
            parts.append(f"{who}: {show(entry['cards'])} ({words})")
        label = self.w.pick("Showdown", "Showdown")
        return self.out("reveal", f"{label}: " + "; ".join(parts), importance=3)

    def handle_pot_awarded(self, event: Event):
        data = event.data
        winners = [p for p, amount in data["shares"].items() if amount > 0]
        if len(winners) == 1:
            who = winners[0]
            how = (
                self.w.pick(f"with {self.shown[who]}, showdown", f"mit {self.shown[who]}, Showdown")
                if who in self.shown
                else self.w.pick("everyone else folded", "alle anderen haben gepasst")
            )
            text = self.w.pick(
                f"Pot {data['amount']} goes to {self.w.who(who)} ({how})",
                f"Pot {data['amount']} geht an {self.w.who(who)} ({how})",
            )
        else:
            split = ", ".join(f"{self.w.who(p)} {a}" for p, a in data["shares"].items() if a > 0)
            text = self.w.pick(
                f"Pot {data['amount']} is split: {split}",
                f"Pot {data['amount']} wird geteilt: {split}",
            )
        return self.out("result", text, importance=3)

    def handle_hand_ended(self, event: Event):
        return self.out(
            "info",
            self.w.pick(
                f"Hand {event.data['hand']} is over", f"Hand {event.data['hand']} ist vorbei"
            ),
            importance=1,
        )

    def handle_players_eliminated(self, event: Event):
        names = self.w.many(event.data["players"])
        return self.out(
            "result",
            self.w.pick(f"{names} is out of chips", f"{names} hat keine Chips mehr"),
            importance=3,
        )

    def handle_match_over(self, event: Event):
        data = event.data
        if data["winner"] is not None:
            who = self.w.who(data["winner"])
            return self.out(
                "result",
                self.w.pick(
                    f"Match over: {who} has all the chips",
                    f"Das Spiel ist aus: {who} hat alle Chips",
                ),
                actor=data["winner"],
                importance=3,
            )
        return self.out(
            "result",
            self.w.pick(
                "Match over: the hand limit is reached",
                "Das Spiel ist aus: das Handlimit ist erreicht",
            ),
            importance=3,
        )

    def handle_talked(self, event: Event):
        who = self.w.who(event.data["player"])
        return self.out(
            "info",
            self.w.pick(f"{who} talks", f"{who} spricht"),
            actor=event.data["player"],
            importance=1,
        )
