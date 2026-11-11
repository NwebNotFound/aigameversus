# ruff: noqa: E501  (lines of prose)
"""Werewolf as a play-by-play."""

import re
from typing import Any

from arena.chronicle.text import CAUSES
from arena.engine.types import Event
from arena.transcript.common import Base
from games.werewolf.selection import load_roles

# How the end reads, per winning side.
SIDES = {
    "en": {
        "wolves": "the werewolves win", "village": "the village wins", "lovers": "the lovers win",
        "white_wolf": "the White Werewolf wins", "nobody": "nobody wins",
    },
    "de": {
        "wolves": "die Werwölfe gewinnen", "village": "das Dorf gewinnt", "lovers": "das Liebespaar gewinnt",
        "white_wolf": "der Weiße Werwolf gewinnt", "nobody": "niemand gewinnt",
    },
}  # fmt: skip


class Werewolf(Base):
    GAME = "werewolf"

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.night = 0
        self.day = 0

    # -- words ---------------------------------------------------------------------

    def role(self, role: str) -> str:
        if self.w.lang == "de":
            return load_roles()[role].name
        return role.replace("_", " ")

    def cause(self, cause: str) -> str:
        return CAUSES[self.w.lang].get(cause, cause.replace("_", " "))

    def selection(self, selection: dict[str, int]) -> str:
        return ", ".join(f"{count}× {self.role(role)}" for role, count in selection.items())

    # -- setup ---------------------------------------------------------------------

    def handle_roles_dealt(self, event: Event):
        text = (
            self.w.pick("Roles dealt", "Rollen verteilt")
            + ": "
            + self.selection(event.data["selection"])
        )
        return self.out("info", text, importance=1)

    def handle_roles_in_play(self, event: Event):
        text = (
            self.w.pick("Roles in play", "Rollen im Spiel")
            + ": "
            + self.selection(event.data["selection"])
        )
        return self.out("reveal", text, importance=2)

    def handle_role_assigned(self, event: Event):
        who = self.w.who(event.data["player"])
        text = self.w.pick(
            f"{who} is the {self.role(event.data['role'])}",
            f"{who} ist {self.role(event.data['role'])}",
        )
        return self.out("info", text, actor=event.data["player"], importance=1)

    def handle_pack_revealed(self, event: Event):
        text = self.w.pick(
            f"The pack knows itself: {self.w.many(event.data['wolves'])}",
            f"Das Rudel kennt sich: {self.w.many(event.data['wolves'])}",
        )
        return self.out("info", text, importance=1)

    # -- night ---------------------------------------------------------------------

    def handle_night_started(self, event: Event):
        self.night = event.data["night"]
        return self.out(
            "heading", self.w.pick(f"Night {self.night}", f"Nacht {self.night}"), importance=2
        )

    def handle_wolf_vote(self, event: Event):
        who, target = self.w.who(event.data["player"]), self.w.who(event.data["target"])
        text = self.w.pick(
            f"Night {self.night}: {who} wants to attack {target}",
            f"Nacht {self.night}: {who} will {target} angreifen",
        )
        return self.out("action", text, actor=event.data["player"], importance=2)

    def handle_wolf_talked(self, event: Event):
        who = self.w.who(event.data["player"])
        return self.out(
            "info",
            self.w.pick(f"{who} talks to the pack", f"{who} spricht zum Rudel"),
            actor=event.data["player"],
            importance=1,
        )

    def handle_seer_inspected(self, event: Event):
        data = event.data
        who, target = self.w.who(data["player"]), self.w.who(data["target"])
        text = self.w.pick(
            f"{who}, the seer, looks at {target}: {self.role(data['role'])}",
            f"{who}, die Seherin, prüft {target}: {self.role(data['role'])}",
        )
        return self.out("reveal", text, actor=data["player"], importance=2)

    def handle_witch_acted(self, event: Event):
        data = event.data
        who = self.w.who(data["player"])
        acts = []
        if data["healed"]:
            acts.append(
                self.w.pick(
                    f"heals {self.w.who(data['healed'])}", f"heilt {self.w.who(data['healed'])}"
                )
            )
        if data["poisoned"]:
            acts.append(
                self.w.pick(
                    f"poisons {self.w.who(data['poisoned'])}",
                    f"vergiftet {self.w.who(data['poisoned'])}",
                )
            )
        what = self.w.pick(" and ", " und ").join(acts) or self.w.pick("does nothing", "tut nichts")
        text = self.w.pick(f"{who}, the witch, {what}", f"{who}, die Hexe, {what}")
        return self.out("action", text, actor=data["player"], importance=2)

    def handle_protected(self, event: Event):
        who, target = self.w.who(event.data["player"]), self.w.who(event.data["target"])
        text = self.w.pick(
            f"{who}, the protector, guards {target}", f"{who}, der Beschützer, schützt {target}"
        )
        return self.out("action", text, actor=event.data["player"], importance=2)

    def handle_spied(self, event: Event):
        data = event.data
        who = self.w.who(data["player"])
        saw = self.w.who(data["wolf"]) if data["wolf"] else self.w.pick("nobody", "niemanden")
        text = self.w.pick(
            f"{who}, the little girl, spies and sees {saw}",
            f"{who}, das kleine Mädchen, spioniert und sieht {saw}",
        )
        return self.out("reveal", text, actor=data["player"], importance=2)

    def handle_girl_caught(self, event: Event):
        who = self.w.who(event.data["player"])
        text = self.w.pick(
            f"{who}, the little girl, is caught spying",
            f"{who}, das kleine Mädchen, wird beim Spionieren erwischt",
        )
        return self.out("reveal", text, actor=event.data["player"], importance=2)

    def handle_raven_chose(self, event: Event):
        who, target = self.w.who(event.data["player"]), self.w.who(event.data["target"])
        text = self.w.pick(
            f"{who}, the raven, marks {target}", f"{who}, der Rabe, markiert {target}"
        )
        return self.out("action", text, actor=event.data["player"], importance=2)

    def handle_white_wolf_chose(self, event: Event):
        who, target = self.w.who(event.data["player"]), self.w.who(event.data["target"])
        text = self.w.pick(
            f"{who}, the White Werewolf, kills the wolf {target}",
            f"{who}, der Weiße Werwolf, tötet den Wolf {target}",
        )
        return self.out("action", text, actor=event.data["player"], importance=2)

    def handle_infection_chosen(self, event: Event):
        who, target = self.w.who(event.data["player"]), self.w.who(event.data["target"])
        text = self.w.pick(
            f"{who}, the prime wolf, infects {target}", f"{who}, der Urwolf, infiziert {target}"
        )
        return self.out("action", text, actor=event.data["player"], importance=2)

    def handle_infected(self, event: Event):
        who = self.w.who(event.data["player"])
        return self.out(
            "reveal",
            self.w.pick(
                f"{who} is infected and joins the pack",
                f"{who} wird infiziert und schließt sich dem Rudel an",
            ),
            actor=event.data["player"],
            importance=2,
        )

    def handle_joined_pack(self, event: Event):
        who = self.w.who(event.data["player"])
        return self.out(
            "reveal",
            self.w.pick(f"{who} joins the pack", f"{who} schließt sich dem Rudel an"),
            actor=event.data["player"],
            importance=2,
        )

    def handle_model_chosen(self, event: Event):
        who, model = self.w.who(event.data["player"]), self.w.who(event.data["model"])
        text = self.w.pick(
            f"{who}, the wild child, takes {model} as the role model",
            f"{who}, das wilde Kind, wählt {model} als Vorbild",
        )
        return self.out("action", text, actor=event.data["player"], importance=2)

    def handle_lovers_linked(self, event: Event):
        data = event.data
        text = self.w.pick(
            f"{self.w.who(data['player'])}, cupid, links the lovers {self.w.many(data['lovers'])}",
            f"{self.w.who(data['player'])}, Amor, verliebt {self.w.many(data['lovers'])}",
        )
        return self.out("action", text, actor=data["player"], importance=2)

    def handle_love_revealed(self, event: Event):
        text = self.w.pick(
            f"The lovers learn about each other: {self.w.many(event.data['lovers'])}",
            f"Das Liebespaar erfährt voneinander: {self.w.many(event.data['lovers'])}",
        )
        return self.out("reveal", text, importance=2)

    def handle_lover_talked(self, event: Event):
        who = self.w.who(event.data["player"])
        return self.out(
            "info",
            self.w.pick(f"{who} talks to the lover", f"{who} spricht zum Liebsten"),
            actor=event.data["player"],
            importance=1,
        )

    def handle_step_done(self, event: Event):
        who = self.w.who(event.data["player"])
        return self.out(
            "info",
            self.w.pick(f"{who} is done", f"{who} ist fertig"),
            actor=event.data["player"],
            importance=1,
        )

    def handle_elder_survived(self, event: Event):
        who = self.w.who(event.data["player"])
        return self.out(
            "reveal",
            self.w.pick(
                f"{who}, the elder, survives the wolves' attack",
                f"{who}, der Dorfälteste, überlebt den Angriff der Wölfe",
            ),
            actor=event.data["player"],
            importance=2,
        )

    # -- morning and day -----------------------------------------------------------

    def handle_morning_started(self, event: Event):
        deaths = event.data["deaths"]
        if not deaths:
            return self.out(
                "result",
                self.w.pick(
                    "Morning: nobody died in the night",
                    "Morgen: niemand ist in der Nacht gestorben",
                ),
                importance=3,
            )
        names = self.w.many(deaths)
        return self.out(
            "result",
            self.w.pick(
                f"Morning: found dead in the night: {names}",
                f"Morgen: in der Nacht gestorben: {names}",
            ),
            importance=3,
        )

    def handle_player_died(self, event: Event):
        data = event.data
        who = self.w.who(data["player"])
        text = self.w.pick(
            f"{who} dies ({self.cause(data['cause'])}); role: {self.role(data['role'])}",
            f"{who} stirbt ({self.cause(data['cause'])}); Rolle: {self.role(data['role'])}",
        )
        return self.out("result", text, actor=data["player"], importance=3)

    def handle_bear_growled(self, event: Event):
        return self.out(
            "reveal",
            self.w.pick(
                "The bear growls: a wolf sits next to the bear tamer",
                "Der Bär brummt: neben dem Bärenführer sitzt ein Wolf",
            ),
            importance=2,
        )

    def handle_raven_mark_announced(self, event: Event):
        target = self.w.who(event.data["target"])
        text = self.w.pick(
            f"The raven has marked {target}: two extra votes against them today",
            f"Der Rabe hat {target} markiert: heute zwei Stimmen mehr gegen diesen Spieler",
        )
        return self.out("reveal", text, importance=2)

    def handle_day_started(self, event: Event):
        self.day = event.data["day"]
        order = self.w.many(event.data["order"])
        text = self.w.pick(f"Day {self.day}", f"Tag {self.day}")
        detail = self.w.pick(f"Speaking order: {order}", f"Redereihenfolge: {order}")
        return self.out("heading", text, detail=detail, importance=2)

    def handle_captain_vote(self, event: Event):
        who, target = self.w.who(event.data["player"]), self.w.who(event.data["target"])
        return self.out(
            "action",
            self.w.pick(
                f"{who} votes for {target} as captain", f"{who} wählt {target} zum Hauptmann"
            ),
            actor=event.data["player"],
            importance=1,
        )

    def handle_captain_elected(self, event: Event):
        data = event.data
        who = self.w.who(data["player"])
        tally = ", ".join(f"{self.w.who(p)} {n}" for p, n in data["votes"].items())
        return self.out(
            "result",
            self.w.pick(f"{who} is elected captain", f"{who} wird zum Hauptmann gewählt"),
            actor=data["player"],
            detail=tally,
            importance=3,
        )

    def handle_captain_passed(self, event: Event):
        data = event.data
        text = self.w.pick(
            f"{self.w.who(data['from'])} passes the captaincy to {self.w.who(data['to'])}",
            f"{self.w.who(data['from'])} gibt das Hauptmannsamt an {self.w.who(data['to'])}",
        )
        return self.out("action", text, actor=data["from"], importance=2)

    def handle_vote_cast(self, event: Event):
        data = event.data
        who = self.w.who(data["player"])
        if data["target"] is None:
            text = self.w.pick(f"{who} abstains", f"{who} enthält sich")
        else:
            text = self.w.pick(
                f"{who} votes for {self.w.who(data['target'])}",
                f"{who} stimmt gegen {self.w.who(data['target'])}",
            )
        return self.out("action", text, actor=data["player"], importance=2)

    def handle_vote_result(self, event: Event):
        data = event.data
        tally = ", ".join(
            f"{self.w.who(p)} {n}" for p, n in sorted(data["counts"].items(), key=lambda kv: -kv[1])
        )
        label = self.w.pick(f"Day {data['day']} vote", f"Abstimmung Tag {data['day']}")
        executed = data["executed"]
        if executed is None:
            text = f"{label}: " + self.w.pick(
                "no majority, nobody is executed", "keine Mehrheit, niemand wird hingerichtet"
            )
        else:
            votes = data["counts"].get(executed, 0)
            text = f"{label}: " + self.w.pick(
                f"{self.w.number(votes, 'vote', 'votes', 'Stimme', 'Stimmen')} against {self.w.who(executed)}, {self.w.who(executed)} is executed",
                f"{self.w.number(votes, 'Stimme', 'Stimmen', 'Stimme', 'Stimmen')} gegen {self.w.who(executed)}, {self.w.who(executed)} wird hingerichtet",
            )
        return self.out("result", text, detail=tally, importance=3)

    def handle_idiot_revealed(self, event: Event):
        who = self.w.who(event.data["player"])
        return self.out(
            "reveal",
            self.w.pick(
                f"{who} is the village idiot and survives, but may no longer vote",
                f"{who} ist der Dorfdepp, überlebt, darf aber nicht mehr abstimmen",
            ),
            actor=event.data["player"],
            importance=3,
        )

    def handle_powers_lost(self, event: Event):
        who = self.w.who(event.data["elder"])
        return self.out(
            "reveal",
            self.w.pick(
                f"{who} the elder is executed: the village roles lose their powers",
                f"{who}, der Dorfälteste, wird hingerichtet: die Dorfrollen verlieren ihre Kräfte",
            ),
            importance=3,
        )

    def handle_hunter_shot(self, event: Event):
        data = event.data
        text = self.w.pick(
            f"{self.w.who(data['player'])}, the hunter, shoots {self.w.who(data['target'])}",
            f"{self.w.who(data['player'])}, der Jäger, erschießt {self.w.who(data['target'])}",
        )
        return self.out("action", text, actor=data["player"], importance=3)

    # -- the narrator and the end -------------------------------------------------

    def handle_narration(self, event: Event):
        # The narrator speaks one language, chosen for the match, and says what other lines say.
        # Show its words only in that language, with the players' names for their seat ids.
        if event.data.get("language") != self.w.lang:
            return None
        text = re.sub(r"\bp\d+\b", lambda m: self.w.who(m.group(0)), event.data["text"])
        return self.out("narration", text, importance=1)

    def handle_game_over(self, event: Event):
        data = event.data
        if data.get("reason") == "night_limit":
            return self.out(
                "result",
                self.w.pick(
                    "Game over: stopped at the night limit",
                    "Spiel aus: beim Nachtlimit abgebrochen",
                ),
                importance=3,
            )
        side = SIDES[self.w.lang].get(data["winner"], data["winner"])
        text = self.w.pick(f"Game over: {side}", f"Spiel aus: {side}")
        return self.out("result", text, detail=self.w.many(data["winners"]), importance=3)
