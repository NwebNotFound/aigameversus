# ruff: noqa: E501  (lines of prose)
"""Liar's Deck as a play-by-play."""

from collections import Counter
from typing import Any

from arena.engine.types import Event
from arena.transcript.common import Base

# Singular and plural of a rank, and the article of the singular, per language.
RANK_WORDS = {
    "en": {
        "king": ("a king", "kings"),
        "queen": ("a queen", "queens"),
        "ace": ("an ace", "aces"),
        "joker": ("a joker", "jokers"),
    },
    "de": {
        "king": ("einen König", "Könige"),
        "queen": ("eine Dame", "Damen"),
        "ace": ("ein Ass", "Asse"),
        "joker": ("einen Joker", "Joker"),
    },
}
TITLE = {
    "en": {"king": "King", "queen": "Queen", "ace": "Ace", "joker": "Joker"},
    "de": {"king": "König", "queen": "Dame", "ace": "Ass", "joker": "Joker"},
}
COUNTS = {
    "en": {2: "two", 3: "three", 4: "four", 5: "five"},
    "de": {2: "zwei", 3: "drei", 4: "vier", 5: "fünf"},
}
PREFIX = {"K": "king", "Q": "queen", "A": "ace", "J": "joker"}
REASONS = {
    "en": {
        "caught_lying": "caught lying",
        "wrong_call": "the call was wrong",
        "devil_card": "the devil card",
    },
    "de": {
        "caught_lying": "beim Lügen erwischt",
        "wrong_call": "der Ruf war falsch",
        "devil_card": "die Teufelskarte",
    },
}


def rank_of(card_id: str) -> str:
    return "joker" if card_id == "DV" else PREFIX[card_id[0]]


class LiarsDeck(Base):
    GAME = "liars_deck"

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.card = ""  # the table card of the round
        self.round_no = 0
        self.caller = ""

    # -- words ---------------------------------------------------------------------

    def rank_phrase(self, ranks: list[str]) -> str:
        """Ranks as words: "a king", "two queens, an ace"."""
        lang = self.w.lang
        parts = []
        for rank, count in Counter(ranks).items():
            single, plural = RANK_WORDS[lang][rank]
            parts.append(single if count == 1 else f"{COUNTS[lang][count]} {plural}")
        return ", ".join(parts)

    def card_names(self, cards: list[str]) -> str:
        lang = self.w.lang
        names = []
        for card in cards:
            if card == "DV":
                names.append(self.w.pick("Devil card", "Teufelskarte"))
            else:
                names.append(f"{TITLE[lang][rank_of(card)]} {card[1:]}".strip())
        return ", ".join(names)

    def table_card_title(self) -> str:
        return TITLE[self.w.lang].get(self.card, self.card)

    # -- events --------------------------------------------------------------------

    def handle_revolver_loaded(self, event: Event):
        chambers = ", ".join(str(n + 1) for n in event.data["live"])
        who = self.w.who(event.data["player"])
        text = self.w.pick(
            f"{who}'s revolver is loaded in chamber {chambers}",
            f"Der Revolver von {who} ist in Kammer {chambers} scharf",
        )
        return self.out("info", text, actor=event.data["player"], importance=1)

    def handle_round_started(self, event: Event):
        data = event.data
        self.card, self.round_no = data["table_card"], data["round"]
        text = self.w.pick(
            f"Round {data['round']}, table card: {self.table_card_title()}",
            f"Runde {data['round']}, Tischkarte: {self.table_card_title()}",
        )
        detail = self.w.pick(
            f"{self.w.who(data['starter'])} starts; players: {self.w.many(data['players'])}",
            f"{self.w.who(data['starter'])} beginnt; Spieler: {self.w.many(data['players'])}",
        )
        return self.out("heading", text, detail=detail, importance=2)

    def handle_hand_dealt(self, event: Event):
        who = self.w.who(event.data["player"])
        text = self.w.pick(
            f"{who} is dealt {self.card_names(event.data['cards'])}",
            f"{who} bekommt {self.card_names(event.data['cards'])}",
        )
        return self.out("info", text, actor=event.data["player"], importance=1)

    def handle_cards_played(self, event: Event):
        data = event.data
        who = self.w.who(data["player"])
        count = data["count"]
        lang = self.w.lang
        single, plural = RANK_WORDS[lang].get(self.card, (self.card, self.card))
        claim = single if count == 1 else f"{COUNTS[lang][count]} {plural}"
        text = self.w.pick(
            f"{who} plays {self.w.number(count, 'card', 'cards', 'Karte', 'Karten')} and claims: {claim}",
            f"{who} legt {self.w.number(count, 'Karte', 'Karten', 'Karte', 'Karten')} ab und behauptet: {claim}",
        )
        return self.out("action", text, actor=data["player"], importance=2)

    def handle_cards_hidden(self, event: Event):
        data = event.data
        cards = data["cards"]
        honest = all(rank_of(c) in (self.card, "joker") for c in cards)
        truth = self.w.pick("true", "wahr") if honest else self.w.pick("a lie", "gelogen")
        text = self.w.pick(
            f"{self.w.who(data['player'])} really plays {self.card_names(cards)} ({truth})",
            f"{self.w.who(data['player'])} legt tatsächlich {self.card_names(cards)} ({truth})",
        )
        return self.out("info", text, actor=data["player"], importance=1)

    def handle_talked(self, event: Event):
        who = self.w.who(event.data["player"])
        return self.out(
            "info",
            self.w.pick(f"{who} talks", f"{who} spricht"),
            actor=event.data["player"],
            importance=1,
        )

    def handle_turn_passed(self, event: Event):
        who = self.w.who(event.data["player"])
        if event.data["auto_call"]:
            text = self.w.pick(
                f"{who} must check the last play", f"{who} muss die letzte Ablage prüfen"
            )
        else:
            text = self.w.pick(f"{who} is next", f"{who} ist an der Reihe")
        return self.out("info", text, actor=event.data["player"], importance=1)

    def handle_liar_called(self, event: Event):
        data = event.data
        self.caller = data["caller"]
        caller, target = self.w.who(data["caller"]), self.w.who(data["target"])
        if data["automatic"]:
            text = self.w.pick(
                f"{caller} has to call LIAR on {target}", f"{caller} muss {target} LÜGNER nennen"
            )
        else:
            text = self.w.pick(
                f"{caller} calls LIAR on {target}", f"{caller} ruft LÜGNER gegen {target}"
            )
        return self.out("action", text, actor=data["caller"], importance=3)

    def handle_cards_revealed(self, event: Event):
        data = event.data
        target = self.w.who(data["player"])
        shown = self.rank_phrase([rank_of(c) for c in data["cards"]])
        if data.get("devil"):
            shown = (
                f"{shown} ({self.w.pick('the devil card among them', 'darunter die Teufelskarte')})"
            )
        verdict = self.w.pick(
            f"{target} told the truth" if data["honest"] else f"{target} was lying",
            f"{target} sagte die Wahrheit" if data["honest"] else f"{target} hat gelogen",
        )
        text = self.w.pick(
            f"The cards show: {shown}. {verdict}", f"Die Karten zeigen: {shown}. {verdict}"
        )
        return self.out(
            "reveal",
            text,
            actor=data["player"],
            detail=self.card_names(data["cards"]),
            importance=3,
        )

    def handle_shooters_chosen(self, event: Event):
        data = event.data
        reason = REASONS[self.w.lang][data["reason"]]
        text = self.w.pick(
            f"{self.w.many(data['players'])} must pull the trigger ({reason})",
            f"{self.w.many(data['players'])} muss abdrücken ({reason})",
        )
        return self.out("info", text, importance=2)

    def handle_trigger_pulled(self, event: Event):
        data = event.data
        who = self.w.who(data["player"])
        shot = self.w.pick("BANG", "PENG") if data["live"] else self.w.pick("click", "klick")
        text = self.w.pick(
            f"{who} pulls the trigger (pull {data['pull']}): {shot}",
            f"{who} drückt ab (Schuss {data['pull']}): {shot}",
        )
        return self.out("result", text, actor=data["player"], importance=3 if data["live"] else 2)

    def handle_players_eliminated(self, event: Event):
        names = self.w.many(event.data["players"])
        text = self.w.pick(f"{names} is out of the game", f"{names} scheidet aus")
        return self.out("result", text, importance=3)

    def handle_round_ended(self, event: Event):
        starter = event.data["next_starter"]
        nxt = (
            self.w.pick(
                f"{self.w.who(starter)} starts the next round",
                f"{self.w.who(starter)} beginnt die nächste Runde",
            )
            if starter
            else ""
        )
        text = self.w.pick(
            f"Round {event.data['round']} is over. {nxt}",
            f"Runde {event.data['round']} ist vorbei. {nxt}",
        )
        return self.out("info", text.strip(), importance=1)

    def handle_match_over(self, event: Event):
        winner = event.data["winner"]
        if winner is None:
            return self.out(
                "result",
                self.w.pick("Match over: nobody is left", "Das Spiel ist aus: niemand ist übrig"),
                importance=3,
            )
        who = self.w.who(winner)
        return self.out(
            "result",
            self.w.pick(
                f"Match over: {who} is the last one standing",
                f"Das Spiel ist aus: {who} bleibt als Letzte(r) übrig",
            ),
            actor=winner,
            importance=3,
        )
