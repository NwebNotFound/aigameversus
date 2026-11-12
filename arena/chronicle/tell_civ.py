"""Words for the facts of a Throne of Tokens match: the fields each template may use.

`fields_of` turns one fact into (template kind, fields); `glance_value` turns a fact of the
"At a glance" box into its text. Nations are called by their display names; the neutral side
(barbarians and rebels) by the template's word for it. Nothing here knows a seat id.
"""

import re
from functools import cache
from typing import Any

from arena.chronicle.digest import Fact
from games.civ.state import NEUTRAL

# The neutral side (barbarians and rebels) is one name, singular, so every verb agrees with it.
NEUTRALS = {"en": "the barbarian horde", "de": "die Barbarenhorde"}
UNITS = {
    "en": ("0 units", "1 unit", "{n} units"),
    "de": ("0 Einheiten", "1 Einheit", "{n} Einheiten"),
}
CITIES = {"en": ("1 city", "{n} cities"), "de": ("1 Stadt", "{n} Städte")}
TREATIES = {"en": ("1 treaty", "{n} treaties"), "de": ("1 Vertrag", "{n} Verträge")}

FIELDS: dict[str, tuple[str, ...]] = {
    "cast": ("cast", "count", "rounds"),
    "age_starts": ("n", "nth", "Nth", "first", "last"),
    "founded_one": ("who",),
    "founded_many": ("who", "count"),
    "conquest": ("taker", "loser"),
    "conquest_capital": ("taker", "loser"),
    "battle_attacker_won": ("attacker", "defender", "lost_attacker", "lost_defender"),
    "battle_defender_won": ("attacker", "defender", "lost_attacker", "lost_defender"),
    "battle_city_held": ("attacker", "defender", "lost_attacker", "lost_defender"),
    "war": ("by", "on"),
    "war_joined": ("by", "on", "joined"),
    "peace": ("a", "b"),
    "treaty": ("a", "b", "treaty"),
    "broken": ("by", "other"),
    "event_plague": ("who",),
    "event_drought": ("who",),
    "event_rebellion": ("who",),
    "event_barbarians": (),
    "gold_rush": ("who", "needed"),
    "talk": ("who", "quote", "quote_bare"),
    "result_domination": ("winners", "round"),
    "result_economy": ("winners", "round"),
    "result_round_limit": ("winners", "round"),
    "ranking": ("ranking",),
}


@cache
def _treaty_names() -> dict[str, dict[str, str]]:
    from games.civ.data_loader import load_civ_data

    treaties = load_civ_data().treaties
    items = treaties.values() if isinstance(treaties, dict) else treaties
    return {t.id: {"en": t.name, "de": t.name_de} for t in items}


def treaty_word(kind: str, lang: str) -> str:
    names = _treaty_names().get(kind)
    return names[lang] if names else kind.replace("_", " ")


def _nation(teller, seat: str | None) -> str:
    return NEUTRALS[teller.lang] if seat == NEUTRAL else teller.who(seat)


def units(n: int, lang: str) -> str:
    none, one, many = UNITS[lang]
    return none if n == 0 else one if n == 1 else many.format(n=n)


def _counted(words: dict[str, tuple[str, str]], n: int, lang: str) -> str:
    one, many = words[lang]
    return one if n == 1 else many.format(n=n)


def finish(text: str, lang: str) -> str:
    """A sentence that starts with the neutral side starts with a capital letter."""
    word = NEUTRALS[lang]
    return re.sub(
        rf"(^|[.!?…]\s+){re.escape(word)}", lambda m: m.group(1) + word[0].upper() + word[1:], text
    )


def fields_of(teller, fact: Fact) -> tuple[str, dict[str, Any]] | None:
    from arena.chronicle.compose import listing, nth

    d, lang = fact.data, teller.lang

    def who(seat: str | None) -> str:
        return _nation(teller, seat)

    match fact.kind:
        case "cast":
            names = listing([who(s) for s in d["players"]], lang)
            return "cast", {"cast": names, "count": len(d["players"]), "rounds": d["rounds"]}
        case "age_starts":
            n = d["n"]
            return "age_starts", {
                "n": n,
                "nth": nth(n, lang),
                "Nth": nth(n, lang).capitalize(),
                "first": d["first"],
                "last": d["last"],
            }
        case "founded":
            if d["count"] == 1:
                return "founded_one", {"who": who(d["who"])}
            return "founded_many", {"who": who(d["who"]), "count": d["count"]}
        case "conquest":
            kind = "conquest_capital" if d["capital"] else "conquest"
            return kind, {"taker": who(d["taker"]), "loser": who(d["loser"])}
        case "battle":
            fields = {
                "attacker": who(d["attacker"]),
                "defender": who(d["defender"]),
                "lost_attacker": units(d["lost_attacker"], lang),
                "lost_defender": units(d["lost_defender"], lang),
            }
            if d["winner"] == d["attacker"]:
                return "battle_attacker_won", fields
            return ("battle_city_held" if d["city"] else "battle_defender_won"), fields
        case "war":
            fields = {"by": who(d["by"]), "on": who(d["on"])}
            if d["joined"]:
                return "war_joined", fields | {
                    "joined": listing([who(s) for s in d["joined"]], lang)
                }
            return "war", fields
        case "treaty":
            if d["ends_war"] or d["kind_id"] == "peace":
                return "peace", {"a": who(d["a"]), "b": who(d["b"])}
            return "treaty", {
                "a": who(d["a"]),
                "b": who(d["b"]),
                "treaty": treaty_word(d["kind_id"], lang),
            }
        case "broken":
            return "broken", {"by": who(d["by"]), "other": who(d["other"])}
        case "event":
            kind = f"event_{d['event']}"
            if kind == "event_barbarians":
                return kind, {}
            if not d["nations"]:
                return None
            return kind, {"who": listing([who(s) for s in d["nations"]], lang)}
        case "gold_rush":
            return "gold_rush", {"who": who(d["who"]), "needed": d["needed"]}
        case "talk":
            quote = teller.quote(d["quote"])
            if not quote:
                return None
            return "talk", teller._quoted({"who": who(d["who"])}, quote)
        case "result":
            winners = listing([who(s) for s in d["winners"]], lang)
            return f"result_{d['kind_id']}", {"winners": winners, "round": d["round"]}
        case "ranking":
            order = [f"{i}. {who(p)} ({score})" for i, (p, score) in enumerate(d["standings"], 1)]
            return "ranking", {"ranking": ", ".join(order)}
    return None


def glance_value(teller, fact: Fact) -> str | None:
    from arena.chronicle.compose import listing

    d, tpl, lang = fact.data, teller.tpl, teller.lang
    values = tpl["glance_values"]

    def who(seat: str | None) -> str:
        return _nation(teller, seat)

    match fact.kind:
        case "winner":
            winners = listing([who(s) for s in d["winners"]], lang)
            return values["winner"][d["kind_id"]].format(winners=winners)
        case "length":
            return values["length"].format(rounds=d["rounds"])
        case "turning_point":
            return tpl["turning_points"][d["type"]].format(
                n=d.get("n", 0),
                taker=who(d.get("taker")),
                loser=who(d.get("loser")),
                attacker=who(d.get("attacker")),
                defender=who(d.get("defender")),
                by=who(d.get("by")),
                on=who(d.get("on")),
                lost=d.get("lost", 0),
            )
        case "conqueror":
            cities = _counted(CITIES, d["cities"], lang)
            return values["conqueror"].format(who=who(d["who"]), cities=cities)
        case "diplomat":
            treaties = _counted(TREATIES, d["treaties"], lang)
            return values["diplomat"].format(who=who(d["who"]), treaties=treaties)
    return None
