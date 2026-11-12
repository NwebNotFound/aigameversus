# ruff: noqa: E501  (lines of prose)
"""Throne of Tokens as a play-by-play: one line per event of games/civ.

Most events are private to one nation, so without spoilers the transcript shows the
rounds, public talk, treaties and wars, conquests, the economic countdown and the end.
"""

from collections.abc import Mapping

from arena.engine.types import Event
from arena.transcript.common import Base

NEUTRAL = "neutral"

EVENTS = {
    "plague": ("plague", "Seuche"),
    "drought": ("drought", "Dürre"),
    "rebellion": ("rebellion", "Aufstand"),
    "barbarians": ("barbarians", "Barbaren"),
    "gold_find": ("gold find", "Goldfund"),
    "good_harvest": ("good harvest", "gute Ernte"),
}


class Civ(Base):
    GAME = "civ"

    def __init__(self, lang, spoilers, names):
        super().__init__(lang, spoilers, names)
        self.armies: dict[str, str] = {}  # army id -> owner, learned from army_raised
        self.cities: dict[str, str] = {}  # city id -> owner
        self.offers: dict[str, str] = {}  # offer id -> sender

    def learn(self, event: Event) -> None:
        data = event.data
        if event.type == "army_raised":
            self.armies[data["army"]] = data["owner"]
        elif event.type == "army_split":
            self.armies[data["new_army"]] = self.armies.get(data["army"], "")
        elif event.type == "city_founded":
            self.cities[data["city"]] = data["owner"]
        elif event.type == "city_conquered":
            self.cities[data["city"]] = data["to"]
        elif event.type in ("treaty_offered", "trade_offered"):
            self.offers[data["offer"]] = data["sender"]
        elif event.type == "random_event" and "army" in data and isinstance(data["army"], dict):
            self.armies[data["army"]["army"]] = NEUTRAL

    # -- words -----------------------------------------------------------------------

    def who(self, nation) -> str:
        if nation == NEUTRAL:
            return self.w.pick("the barbarians", "die Barbaren")
        return self.w.who(nation)

    def amounts(self, amounts: Mapping[str, int]) -> str:
        names = {
            "food": ("food", "Nahrung"),
            "wood": ("wood", "Holz"),
            "iron": ("iron", "Eisen"),
            "gold": ("gold", "Gold"),
        }
        parts = [f"{n} {self.w.pick(*names.get(r, (r, r)))}" for r, n in amounts.items() if n]
        return ", ".join(parts) or self.w.pick("nothing", "nichts")

    def tile(self, tile) -> str:
        return f"({tile[0]}, {tile[1]})"

    def army_owner(self, army: str) -> str | None:
        return self.armies.get(army)

    def city_owner(self, city: str) -> str | None:
        return self.cities.get(city)

    # -- the round -------------------------------------------------------------------

    def handle_round_started(self, event: Event):
        n = event.data["round"]
        return self.out("heading", self.w.pick(f"Round {n}", f"Runde {n}"), importance=2)

    def handle_map_drawn(self, event: Event):
        rows = event.data["rows"]
        size = f"{len(rows[0]) if rows else 0} × {len(rows)}"
        return self.out(
            "info",
            self.w.pick(f"The map is drawn ({size} tiles)", f"Die Karte entsteht ({size} Felder)"),
            importance=1,
        )

    def handle_plan_set(self, event: Event):
        nation, plan = event.data["nation"], event.data["plan"]
        if plan is None:
            return None
        return self.out(
            "thought",
            self.w.pick(f"{self.who(nation)} plans: {plan}", f"{self.who(nation)} plant: {plan}"),
            actor=nation,
            importance=1,
        )

    def handle_order_refused(self, event: Event):
        data = event.data
        kind = str(data["order"].get("type", "?")).replace("_", " ")
        return self.out(
            "info",
            self.w.pick(
                f"Order of {self.who(data['nation'])} dropped ({kind})",
                f"Befehl von {self.who(data['nation'])} verworfen ({kind})",
            ),
            actor=data["nation"],
            detail=data["reason"],
            importance=1,
        )

    # -- cities ----------------------------------------------------------------------

    def handle_city_founded(self, event: Event):
        data = event.data
        self.cities[data["city"]] = data["owner"]
        where = self.tile((data["col"], data["row"]))
        return self.out(
            "action",
            self.w.pick(
                f"{self.who(data['owner'])} founds {data['city']} at {where}",
                f"{self.who(data['owner'])} gründet {data['city']} auf {where}",
            ),
            actor=data["owner"],
        )

    def handle_city_focus_set(self, event: Event):
        data = event.data
        owner = self.city_owner(data["city"])
        return self.out(
            "action",
            self.w.pick(
                f"{data['city']} now works for {data['focus']}",
                f"{data['city']} arbeitet jetzt für {data['focus']}",
            ),
            actor=owner,
            importance=1,
        )

    def handle_building_started(self, event: Event):
        data = event.data
        return self.out(
            "action",
            self.w.pick(
                f"{data['city']} starts a {data['building']} ({self.amounts(data['cost'])})",
                f"{data['city']} beginnt {data['building']} ({self.amounts(data['cost'])})",
            ),
            actor=self.city_owner(data["city"]),
        )

    def handle_construction_progressed(self, event: Event):
        city = event.data["city"]
        return self.out(
            "info",
            self.w.pick(f"Building goes on in {city}", f"In {city} wird weitergebaut"),
            actor=self.city_owner(city),
            importance=1,
        )

    def handle_building_completed(self, event: Event):
        data = event.data
        return self.out(
            "action",
            self.w.pick(
                f"{data['city']} finishes its {data['building']}",
                f"{data['city']} stellt {data['building']} fertig",
            ),
            actor=self.city_owner(data["city"]),
        )

    def handle_building_demolished(self, event: Event):
        data = event.data
        return self.out(
            "action",
            self.w.pick(
                f"{data['city']} tears down its {data['building']} (back: {self.amounts(data['refund'])})",
                f"{data['city']} reißt {data['building']} ab (zurück: {self.amounts(data['refund'])})",
            ),
            actor=self.city_owner(data["city"]),
        )

    def handle_production(self, event: Event):
        data = event.data
        return self.out(
            "info",
            self.w.pick(
                f"{self.who(data['player'])} produces {self.amounts(data['yields'])}",
                f"{self.who(data['player'])} erzeugt {self.amounts(data['yields'])}",
            ),
            actor=data["player"],
            detail=self.w.pick("stock: ", "Vorrat: ") + self.amounts(data["stock"]),
            importance=1,
        )

    def handle_city_grew(self, event: Event):
        data = event.data
        return self.out(
            "info",
            self.w.pick(
                f"{data['city']} grows to {data['population']}",
                f"{data['city']} wächst auf {data['population']}",
            ),
            actor=self.city_owner(data["city"]),
            importance=1,
        )

    # -- armies ----------------------------------------------------------------------

    def handle_army_raised(self, event: Event):
        data = event.data
        self.armies[data["army"]] = data["owner"]
        units = ", ".join(u["kind"] for u in data["units"])
        return self.out(
            "action",
            self.w.pick(
                f"{self.who(data['owner'])} raises {data['army']} ({units})",
                f"{self.who(data['owner'])} stellt {data['army']} auf ({units})",
            ),
            actor=data["owner"],
        )

    def handle_army_moved(self, event: Event):
        data = event.data
        to = self.tile(data["path"][-1]) if data["path"] else "?"
        return self.out(
            "action",
            self.w.pick(f"{data['army']} moves to {to}", f"{data['army']} zieht nach {to}"),
            actor=self.army_owner(data["army"]),
            importance=1,
        )

    def handle_army_split(self, event: Event):
        data = event.data
        self.armies[data["new_army"]] = self.armies.get(data["army"], "")
        return self.out(
            "action",
            self.w.pick(
                f"{data['new_army']} splits off from {data['army']}",
                f"{data['new_army']} spaltet sich von {data['army']} ab",
            ),
            actor=self.army_owner(data["army"]),
            importance=1,
        )

    def handle_armies_merged(self, event: Event):
        data = event.data
        joined = ", ".join(data["armies"])
        return self.out(
            "action",
            self.w.pick(
                f"{joined} join {data['into']}", f"{joined} schließen sich {data['into']} an"
            ),
            actor=self.army_owner(data["into"]),
            importance=1,
        )

    def handle_army_disbanded(self, event: Event):
        army = event.data["army"]
        return self.out(
            "action",
            self.w.pick(f"{army} is disbanded", f"{army} wird aufgelöst"),
            actor=self.army_owner(army),
            importance=1,
        )

    def handle_units_lost(self, event: Event):
        data = event.data
        count = len(data["indexes"])
        reasons = {
            "settled": ("a settler founds a city", "ein Siedler gründet eine Stadt"),
            "battle": ("in battle", "im Kampf"),
            "starved": ("to hunger", "durch Hunger"),
        }
        why = self.w.pick(*reasons.get(data["reason"], (data["reason"], data["reason"])))
        units = self.w.number(count, "unit", "units", "Einheit", "Einheiten")
        return self.out(
            "info",
            self.w.pick(
                f"{data['army']} loses {units} ({why})", f"{data['army']} verliert {units} ({why})"
            ),
            actor=self.army_owner(data["army"]),
            importance=1,
        )

    def handle_army_fortified(self, event: Event):
        army = event.data["army"]
        return self.out(
            "action",
            self.w.pick(f"{army} digs in", f"{army} verschanzt sich"),
            actor=self.army_owner(army),
            importance=1,
        )

    # -- war -------------------------------------------------------------------------

    def handle_attack_ordered(self, event: Event):
        data = event.data
        return self.out(
            "action",
            self.w.pick(
                f"{data['army']} attacks {self.tile(data['target'])}",
                f"{data['army']} greift {self.tile(data['target'])} an",
            ),
            actor=self.army_owner(data["army"]),
        )

    def handle_attack_called_off(self, event: Event):
        data = event.data
        return self.out(
            "info",
            self.w.pick(
                f"The attack of {data['army']} is called off ({data['reason']})",
                f"Der Angriff von {data['army']} fällt aus ({data['reason']})",
            ),
            actor=self.army_owner(data["army"]),
            importance=1,
        )

    def handle_battle(self, event: Event):
        data = event.data
        a, d = data["attacker"], data["defender"]
        lost = self.w.pick(
            f"{self.who(a['nation'])} lost {len(a['lost'])}, {self.who(d['nation'])} lost {len(d['lost'])}",
            f"{self.who(a['nation'])} verlor {len(a['lost'])}, {self.who(d['nation'])} verlor {len(d['lost'])}",
        )
        return self.out(
            "result",
            self.w.pick(
                f"Battle at {self.tile(data['tile'])}: {self.who(a['nation'])} against {self.who(d['nation'])}, {self.who(data['winner'])} wins",
                f"Schlacht bei {self.tile(data['tile'])}: {self.who(a['nation'])} gegen {self.who(d['nation'])}, {self.who(data['winner'])} siegt",
            ),
            actor=a["nation"],
            detail=lost,
            importance=3,
        )

    def handle_city_conquered(self, event: Event):
        data = event.data
        self.cities[data["city"]] = data["to"]
        return self.out(
            "result",
            self.w.pick(
                f"{self.who(data['to'])} takes {data['city']} from {self.who(data['from'])}",
                f"{self.who(data['to'])} erobert {data['city']} von {self.who(data['from'])}",
            ),
            actor=data["to"],
            importance=3,
        )

    def handle_city_pillaged(self, event: Event):
        data = event.data
        return self.out(
            "action",
            self.w.pick(
                f"{data['army']} burns the {data['building']} of {data['city']} (loot: {self.amounts(data['loot'])})",
                f"{data['army']} brennt {data['building']} in {data['city']} nieder (Beute: {self.amounts(data['loot'])})",
            ),
            actor=data["by"],
            importance=3,
        )

    def handle_war_weariness(self, event: Event):
        data = event.data
        share = round(-data["modifier"] * 100)
        return self.out(
            "info",
            self.w.pick(
                f"{self.who(data['nation'])} is weary of war: production −{share} %",
                f"{self.who(data['nation'])} ist kriegsmüde: Produktion −{share} %",
            ),
            actor=data["nation"],
            importance=1,
        )

    # -- diplomacy -------------------------------------------------------------------

    def handle_treaty_offered(self, event: Event):
        data = event.data
        self.offers[data["offer"]] = data["sender"]
        return self.out(
            "action",
            self.w.pick(
                f"{self.who(data['sender'])} offers {self.who(data['to'])} a {data['treaty']} treaty",
                f"{self.who(data['sender'])} bietet {self.who(data['to'])} einen Vertrag an: {data['treaty']}",
            ),
            actor=data["sender"],
        )

    def handle_trade_offered(self, event: Event):
        data = event.data
        self.offers[data["offer"]] = data["sender"]
        return self.out(
            "action",
            self.w.pick(
                f"{self.who(data['sender'])} offers {self.who(data['to'])} {self.amounts(data['gives'])} for {self.amounts(data['wants'])}",
                f"{self.who(data['sender'])} bietet {self.who(data['to'])} {self.amounts(data['gives'])} für {self.amounts(data['wants'])}",
            ),
            actor=data["sender"],
        )

    def _answer(self, event: Event, en: str, de: str):
        offer = event.data["offer"]
        return self.out(
            "action",
            self.w.pick(f"Offer {offer} {en}", f"Angebot {offer} {de}"),
            actor=self.offers.get(offer),
            importance=1,
        )

    def handle_treaty_declined(self, event: Event):
        return self._answer(event, "is declined", "wird abgelehnt")

    def handle_trade_declined(self, event: Event):
        return self._answer(event, "is declined", "wird abgelehnt")

    def handle_trade_agreed(self, event: Event):
        return self._answer(event, "is accepted", "wird angenommen")

    def handle_offer_lapsed(self, event: Event):
        return self._answer(event, "lapses unanswered", "verfällt unbeantwortet")

    def handle_treaty_signed(self, event: Event):
        data = event.data
        return self.out(
            "result",
            self.w.pick(
                f"{self.w.many(data['parties'])} sign a {data['kind']} treaty",
                f"{self.w.many(data['parties'])} schließen einen Vertrag: {data['kind']}",
            ),
            importance=3,
        )

    def handle_treaty_expired(self, event: Event):
        treaty = event.data["treaty"]
        return self.out(
            "info",
            self.w.pick(f"Treaty {treaty} runs out", f"Vertrag {treaty} läuft aus"),
            importance=1,
        )

    def handle_treaty_broken(self, event: Event):
        data = event.data
        return self.out(
            "result",
            self.w.pick(
                f"{self.who(data['by'])} breaks treaty {data['treaty']} (reputation {data['reputation']})",
                f"{self.who(data['by'])} bricht Vertrag {data['treaty']} (Ruf {data['reputation']})",
            ),
            actor=data["by"],
            importance=3,
        )

    def handle_war_declared(self, event: Event):
        data = event.data
        joined = (
            self.w.pick(" Joining them: ", " An ihrer Seite: ") + self.w.many(data["joined"])
            if data.get("joined")
            else ""
        )
        return self.out(
            "result",
            self.w.pick(
                f"{self.who(data['by'])} declares war on {self.who(data['on'])}.{joined}",
                f"{self.who(data['by'])} erklärt {self.who(data['on'])} den Krieg.{joined}",
            ),
            actor=data["by"],
            importance=3,
        )

    def handle_tribute_paid(self, event: Event):
        data = event.data
        return self.out(
            "info",
            self.w.pick(
                f"{self.who(data['payer'])} pays {self.who(data['payee'])} tribute: {self.amounts(data['paid'])}",
                f"{self.who(data['payer'])} zahlt {self.who(data['payee'])} Tribut: {self.amounts(data['paid'])}",
            ),
            actor=data["payer"],
            importance=1,
        )

    def handle_trade_failed(self, event: Event):
        deal = event.data["deal"]
        return self.out(
            "info",
            self.w.pick(
                f"Trade {deal} fails: not enough to hand over",
                f"Handel {deal} scheitert: nicht genug zum Übergeben",
            ),
            actor=self.offers.get(deal),
            importance=2,
        )

    def handle_trade_done(self, event: Event):
        deal = event.data["deal"]
        return self.out(
            "info",
            self.w.pick(f"Trade {deal} is carried out", f"Handel {deal} wird ausgeführt"),
            actor=self.offers.get(deal),
            importance=1,
        )

    # -- events and the end ----------------------------------------------------------

    def handle_random_event(self, event: Event):
        data = event.data
        name = self.w.pick(*EVENTS.get(data["event"], (data["event"], data["event"])))
        place = data.get("city") or self.who(data.get("nation"))
        if data["event"] == "rebellion":
            self.cities[data["city"]] = NEUTRAL
        if isinstance(data.get("army"), dict):
            army = data["army"]
            self.armies[army["army"]] = NEUTRAL
            place = self.tile((army["col"], army["row"]))
        elif "condition" in data:
            condition = data["condition"]
            place = self.tile((condition["col"], condition["row"]))
        return self.out(
            "result",
            self.w.pick(f"Event: {name} ({place})", f"Ereignis: {name} ({place})"),
            importance=2,
        )

    def handle_economy_countdown(self, event: Event):
        data = event.data
        holding = {n: r for n, r in data["rounds"].items() if r}
        if not holding:
            return self.out(
                "info",
                self.w.pick("Nobody holds the gold any more", "Niemand hält mehr das Gold"),
                importance=2,
            )
        parts = ", ".join(f"{self.who(n)} {r}/{data['needed']}" for n, r in holding.items())
        return self.out(
            "reveal",
            self.w.pick(f"Gold countdown: {parts}", f"Gold-Countdown: {parts}"),
            importance=3,
        )

    def handle_victory(self, event: Event):
        data = event.data
        kinds = {
            "domination": ("by domination", "durch Vorherrschaft"),
            "economy": ("by wealth", "durch Reichtum"),
            "round_limit": (
                "on points after the last round",
                "nach Punkten nach der letzten Runde",
            ),
        }
        how = self.w.pick(*kinds.get(data["kind"], (data["kind"], data["kind"])))
        scores = ", ".join(f"{self.who(s['player'])} {s['score']}" for s in data["standings"])
        return self.out(
            "result",
            self.w.pick(
                f"{self.w.many(data['winners'])} wins {how}",
                f"{self.w.many(data['winners'])} gewinnt {how}",
            ),
            detail=self.w.pick("Scores: ", "Punkte: ") + scores,
            importance=3,
        )
