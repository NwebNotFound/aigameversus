# ruff: noqa: E501  (lines of prose)
"""High Card, the reference game, as a play-by-play."""

from arena.engine.types import Event
from arena.transcript.common import Base


class Toy(Base):
    GAME = "toy"

    def handle_hand_dealt(self, event: Event):
        who = self.w.who(event.data["player"])
        cards = ", ".join(str(c) for c in event.data["cards"])
        text = self.w.pick(f"{who} is dealt {cards}", f"{who} bekommt {cards}")
        return self.out("info", text, actor=event.data["player"], importance=1)

    def handle_card_played(self, event: Event):
        who = self.w.who(event.data["player"])
        text = self.w.pick(
            f"{who} plays {event.data['card']}", f"{who} spielt {event.data['card']}"
        )
        return self.out("action", text, actor=event.data["player"], importance=2)

    def handle_trick_won(self, event: Event):
        who = self.w.who(event.data["player"])
        cards = ", ".join(f"{self.w.who(p)} {c}" for p, c in event.data["cards"].items())
        text = self.w.pick(f"{who} wins the trick", f"{who} gewinnt den Stich")
        return self.out("result", text, actor=event.data["player"], detail=cards, importance=3)
