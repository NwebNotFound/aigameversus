"""Words for the facts of a Liar's Deck match: the fields each template may use.

`fields_of` turns one fact into (template kind, fields); `glance_value` turns a fact of the
"At a glance" box into its text. Both use the teller's names, language and picker; nothing here
knows a seat id.
"""

from typing import Any

from arena.chronicle.digest import Fact

CARD_WORDS = {
    "en": {"K": "king", "Q": "queen", "A": "ace", "J": "joker", "DV": "devil card"},
    "de": {"K": "König", "Q": "Dame", "A": "Ass", "J": "Joker", "DV": "Teufelskarte"},
}
CARD_PLURALS = {
    "en": {"K": "kings", "Q": "queens", "A": "aces", "J": "jokers", "DV": "devil cards"},
    "de": {"K": "Könige", "Q": "Damen", "A": "Asse", "J": "Joker", "DV": "Teufelskarten"},
}
TABLE_CARDS = {"king": "K", "queen": "Q", "ace": "A"}
CLOSE_CALL = 1 / 3  # a survived shot at least this likely to be live gets its own words

FIELDS: dict[str, tuple[str, ...]] = {
    "cast": ("cast", "count"),
    "cast_devil": ("cast", "count"),
    "round_starts": ("n", "nth", "Nth", "card", "card_pl", "alive", "starter"),
    "duel": ("a", "b", "n"),
    "lie_big": ("who", "count", "false_cards", "card", "card_pl"),
    "truth_big": ("who", "count", "card", "card_pl"),
    "claim_quote": ("who", "quote", "quote_bare"),
    "call": ("caller", "target"),
    "call_auto": ("caller", "target"),
    "reveal_caught": ("caller", "target", "cards", "card", "card_pl", "n_false"),
    "reveal_wrong": ("caller", "target", "cards", "card", "card_pl"),
    "devil_revealed": ("caller", "target", "cards"),
    "trigger_click": ("player", "pull", "odds"),
    "trigger_close": ("player", "pull", "odds"),
    "trigger_bang": ("player", "pull", "odds"),
    "eliminated": ("player", "place", "n"),
    "result": ("winner", "rounds"),
    "ranking": ("ranking",),
}


def _ordinal(n: int | None, lang: str) -> str:
    if n is None:
        return ""
    if lang == "de":
        return f"Platz {n}"
    if 10 <= n % 100 <= 20:
        return f"{n}th"
    return f"{n}" + {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")


def _odds(risk: float, lang: str) -> str:
    n = round(1 / risk) if risk else 0
    return f"1 zu {n}" if lang == "de" else f"1 in {n}"


def _card(teller, table_card: str | None, plural: bool = False) -> str:
    words = (CARD_PLURALS if plural else CARD_WORDS)[teller.lang]
    return words.get(TABLE_CARDS.get(table_card or "", ""), "")


def _cards(teller, ids: list[str]) -> str:
    """Card ids as words: ["K4", "J2"] as "king, joker"."""
    words = CARD_WORDS[teller.lang]
    return ", ".join(words["DV" if i == "DV" else i[0]] for i in ids)


def fields_of(teller, fact: Fact) -> tuple[str, dict[str, Any]] | None:
    from arena.chronicle.compose import listing, nth

    d, who, lang = fact.data, teller.who, teller.lang
    table = getattr(teller, "table_card", None)
    match fact.kind:
        case "cast":
            kind = "cast_devil" if "devil" in (d.get("variant") or "") else "cast"
            names = listing([who(s) for s in d["players"]], lang)
            return kind, {"cast": names, "count": len(d["players"])}
        case "round_starts":
            teller.table_card = d["card"]
            n = d["n"]
            return "round_starts", {
                "n": n,
                "nth": nth(n, lang),
                "Nth": nth(n, lang).capitalize(),
                "card": _card(teller, d["card"]),
                "card_pl": _card(teller, d["card"], plural=True),
                "alive": d["alive"],
                "starter": who(d["starter"]),
            }
        case "duel":
            return "duel", {"a": who(d["a"]), "b": who(d["b"]), "n": d["n"]}
        case "lie_big" | "truth_big":
            fields = {
                "who": who(d["who"]),
                "count": d["count"],
                "card": _card(teller, table),
                "card_pl": _card(teller, table, plural=True),
            }
            if fact.kind == "lie_big":
                fields["false_cards"] = d["false_cards"]
            return fact.kind, fields
        case "claim_quote":
            quote = teller.quote(d["quote"])
            if not quote:
                return None
            return "claim_quote", teller._quoted({"who": who(d["who"])}, quote)
        case "call":
            kind = "call_auto" if d["automatic"] else "call"
            return kind, {"caller": who(d["caller"]), "target": who(d["target"])}
        case "reveal":
            fields = {
                "caller": who(d["caller"]),
                "target": who(d["target"]),
                "cards": _cards(teller, d["cards"]),
            }
            if d["devil"]:
                return "devil_revealed", fields
            fields |= {"card": _card(teller, table), "card_pl": _card(teller, table, plural=True)}
            if d["honest"]:
                return "reveal_wrong", fields
            return "reveal_caught", fields | {"n_false": d["n_false"]}
        case "trigger":
            if d["live"]:
                kind = "trigger_bang"
            else:
                kind = "trigger_close" if d["risk"] >= CLOSE_CALL else "trigger_click"
            fields = {"player": who(d["player"]), "pull": d["pull"], "odds": _odds(d["risk"], lang)}
            return kind, fields
        case "eliminated":
            fields = {"player": who(d["player"]), "place": _ordinal(d["place"], lang), "n": d["n"]}
            return "eliminated", fields
        case "result":
            return "result", {"winner": who(d["winner"]), "rounds": d["rounds"]}
        case "ranking":
            order = [f"{i}. {who(p)}" for i, p in enumerate(d["ranking"], start=1)]
            return "ranking", {"ranking": ", ".join(order)}
    return None  # devil_shots is told with the reveal of the devil card


def glance_value(teller, fact: Fact) -> str | None:
    d, who, tpl = fact.data, teller.who, teller.tpl
    values = tpl["glance_values"]
    match fact.kind:
        case "winner":
            return who(d["winner"])
        case "length":
            return values["length"].format(rounds=d["rounds"])
        case "turning_point":
            return tpl["turning_points"][d["type"]].format(
                n=d.get("n", 0),
                player=who(d.get("player")),
                target=who(d.get("target")),
                caller=who(d.get("caller")),
                winner=who(d.get("winner")),
                loser=who(d.get("loser")),
                count=d.get("count", 0),
                odds=_odds(d["risk"], teller.lang) if "risk" in d else "",
            )
        case "bluffer":
            return values["bluffer"].format(who=who(d["who"]), lies=d["lies"], plays=d["plays"])
        case "caller":
            return values["caller"].format(who=who(d["who"]), right=d["right"], of=d["of"])
        case "survivor":
            return values["survivor"].format(who=who(d["who"]), shots=d["shots"])
    return None
