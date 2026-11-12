"""Words for the facts of a Poker match: the fields each template may use.

`fields_of` turns one fact into (template kind, fields); `glance_value` turns a fact of the
"At a glance" box into its text. Hand names are written to follow "with" in English and
"mit" in German (dative), the only way the templates use them. Nothing here knows a seat id.
"""

from typing import Any

from arena.chronicle.digest import Fact
from arena.chronicle.tell_liars_deck import _ordinal

HANDS = {
    "en": {
        "high_card": "nothing but high card",
        "one_pair": "a pair",
        "two_pair": "two pair",
        "three_of_a_kind": "three of a kind",
        "straight": "a straight",
        "flush": "a flush",
        "full_house": "a full house",
        "four_of_a_kind": "four of a kind",
        "straight_flush": "a straight flush",
        "royal_flush": "a royal flush",
    },
    "de": {
        "high_card": "nichts als der höchsten Karte",
        "one_pair": "einem Paar",
        "two_pair": "zwei Paaren",
        "three_of_a_kind": "einem Drilling",
        "straight": "einer Straße",
        "flush": "einem Flush",
        "full_house": "einem Full House",
        "four_of_a_kind": "einem Vierling",
        "straight_flush": "einem Straight Flush",
        "royal_flush": "einem Royal Flush",
    },
}

_POT = ("winner", "amount", "big_blinds", "hand")
FIELDS: dict[str, tuple[str, ...]] = {
    "cast": ("cast", "count", "stack", "hands"),
    "blinds_open": ("small", "big"),
    "level_starts": ("n", "nth", "Nth", "first", "small", "big", "players"),
    "pot_showdown": (*_POT, "with_hand", "loser", "loser_hand"),
    "pot_allin": (*_POT, "allin", "with_hand", "loser", "loser_hand"),
    "pot_bluff": _POT,
    "pot_won": _POT,
    "pot_split": ("amount", "hand"),
    "busted": ("player", "place", "hand"),
    "talk": ("who", "quote", "quote_bare"),
    "result_winner": ("winner", "hands"),
    "result_limit": ("leaders", "hands"),
    "ranking": ("ranking",),
}


def hand_words(hand: str | None, lang: str) -> str:
    return HANDS[lang].get(hand or "", (hand or "").replace("_", " "))


def fields_of(teller, fact: Fact) -> tuple[str, dict[str, Any]] | None:
    from arena.chronicle.compose import listing, nth

    d, who, lang = fact.data, teller.who, teller.lang
    match fact.kind:
        case "cast":
            names = listing([who(s) for s in d["players"]], lang)
            return "cast", {
                "cast": names,
                "count": len(d["players"]),
                "stack": d["stack"],
                "hands": d["hands"],
            }
        case "level_starts":
            n = d["n"]
            if n == 1:  # the blinds the tournament starts with: nothing has risen yet
                return "blinds_open", {"small": d["small"], "big": d["big"]}
            return "level_starts", {
                "n": n,
                "nth": nth(n, lang),
                "Nth": nth(n, lang).capitalize(),
                "first": d["first"],
                "small": d["small"],
                "big": d["big"],
                "players": d["players"],
            }
        case "pot":
            pot = {
                "winner": who(d["winner"]),
                "amount": d["amount"],
                "big_blinds": d["big_blinds"],
                "hand": d["hand"],
            }
            if d["split"]:
                return "pot_split", {"amount": d["amount"], "hand": d["hand"]}
            if d["showdown"] and d["loser"]:
                shown = {
                    "with_hand": hand_words(d["with"], lang),
                    "loser": who(d["loser"]),
                    "loser_hand": hand_words(d["loser_with"], lang),
                }
                if d["allin"]:
                    allin = listing([who(s) for s in d["allin"]], lang)
                    return "pot_allin", pot | shown | {"allin": allin}
                return "pot_showdown", pot | shown
            return ("pot_bluff" if d["bluff"] else "pot_won"), pot
        case "busted":
            return "busted", {
                "player": who(d["player"]),
                "place": _ordinal(d["place"], lang),
                "hand": d["hand"],
            }
        case "talk":
            quote = teller.quote(d["quote"])
            if not quote:
                return None
            return "talk", teller._quoted({"who": who(d["who"])}, quote)
        case "result":
            if d["winner"]:
                return "result_winner", {"winner": who(d["winner"]), "hands": d["hands"]}
            leaders = listing([who(s) for s in d["leaders"]], lang)
            return "result_limit", {"leaders": leaders, "hands": d["hands"]}
        case "ranking":
            order = [f"{i}. {who(p)}" for i, p in enumerate(d["ranking"], start=1)]
            return "ranking", {"ranking": ", ".join(order)}
    return None


def glance_value(teller, fact: Fact) -> str | None:
    from arena.chronicle.compose import listing

    d, who, tpl, lang = fact.data, teller.who, teller.tpl, teller.lang
    values = tpl["glance_values"]
    match fact.kind:
        case "winner":
            if d["winner"]:
                return values["winner"].format(winner=who(d["winner"]))
            leaders = listing([who(s) for s in d["leaders"]], lang)
            return values["leader"].format(leaders=leaders)
        case "length":
            return values["length"].format(hands=d["hands"])
        case "turning_point":
            return tpl["turning_points"]["pot"].format(
                level=d["level"], hand=d["hand"], winner=who(d["winner"]), amount=d["amount"]
            )
        case "best_hand":
            return values["best_hand"].format(
                who=who(d["who"]), with_hand=hand_words(d["with"], lang)
            )
        case "aggressor":
            return values["aggressor"].format(who=who(d["who"]), moves=d["moves"])
    return None
