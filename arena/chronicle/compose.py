"""From a digest to a story: words for the facts, in a style and a language.

Every kind of fact has several variants per style (`templates/<game>.<lang>.yaml`). The
variant is picked by a random stream seeded with the match seed, the style and the language,
and a finished sentence is never used twice in one chronicle, so a long match does not
repeat itself and the same log always tells the same story.

Names are display names (`names`: seat to the name shown everywhere); a seat id never reaches
the text, not even inside a quote.
"""

import random
import re
from collections.abc import Mapping
from functools import cache
from importlib import resources
from typing import Any

import yaml

from arena.chronicle import tell_civ, tell_liars_deck
from arena.chronicle.digest import Digest, Fact
from arena.chronicle.text import CAUSES
from games.werewolf.selection import load_roles

STYLES = ("epic", "news", "sports", "novel")
LANGS = ("en", "de")
SEAT = re.compile(r"\bp\d{1,2}\b", re.IGNORECASE)
MIN_QUOTE_WORDS = 4  # a quote shorter than this says nothing worth quoting
SENTENCES = re.compile(r"(?<=[.!?…])\s+")

NTH = {
    "en": "first second third fourth fifth sixth seventh eighth ninth tenth eleventh twelfth",
    "de": "erste zweite dritte vierte fünfte sechste siebte achte neunte zehnte elfte zwölfte",
}
NTH = {lang: words.split() for lang, words in NTH.items()}
SIDES = {
    "en": {
        "wolves": "The wolves",
        "village": "The village",
        "lovers": "The lovers",
        "white_wolf": "The White Werewolf",
        "nobody": "Nobody",
    },
    "de": {
        "wolves": "Die Wölfe",
        "village": "Das Dorf",
        "lovers": "Das Liebespaar",
        "white_wolf": "Der Weiße Werwolf",
        "nobody": "Niemand",
    },
}
# German articles by role: (definite, indefinite) in the nominative.
DE_ARTICLES = {"seer": ("die", "eine"), "witch": ("die", "eine"), "little_girl": ("das", "ein")}
DE_ARTICLES |= {"wild_child": ("das", "ein")}
_ROLE = ("role", "role_the", "role_a", "role_acc")
# The fields a template of each kind may use; the tests format every variant against them.
FIELDS: dict[str, tuple[str, ...]] = {
    "cast": ("cast", "count"),
    "lovers": ("a", "b", "by"),
    "night_falls": ("n", "nth", "Nth", "alive"),
    "day_breaks": ("n", "nth", "Nth", "alive"),
    "wolf_plan": ("who", "quote", "quote_bare"),
    "wolf_target": ("target",),
    "wolf_missed_witch": ("target",),
    "wolf_missed_protector": ("target",),
    "wolf_missed_unknown": ("target",),
    "seer_found_wolf": ("seer", "target", *_ROLE),
    "seer_found_village": ("seer", "target", *_ROLE),
    "witch_heal": ("witch", "target"),
    "witch_poison": ("witch", "target"),
    "night_quiet": (),
    "death_wolves": ("player", "cause", *_ROLE),
    "death_poison": ("player", "cause", *_ROLE),
    "death_grief": ("player", "cause", *_ROLE),
    "death_other": ("player", "cause", *_ROLE),
    "hunter_shot": ("hunter", "target"),
    "captain": ("player", "votes"),
    "vote_reason": ("who", "target", "quote", "quote_bare"),
    "speech_own": ("who", "quote", "quote_bare"),
    "speech_accuser": ("who", "focus", "quote", "quote_bare"),
    "tally_decided": ("tally", "executed", "votes"),
    "tally_none": ("tally", "executed", "votes"),
    "execution_wrong": ("player", "votes", *_ROLE),
    "execution_wolf": ("player", "votes", *_ROLE),
    "execution_other": ("player", "votes", *_ROLE),
    "no_execution": (),
    "claim_lie": (
        "who",
        "claimed",
        "claimed_the",
        "claimed_a",
        "claimed_acc",
        "actual",
        "actual_the",
        "actual_a",
        "actual_acc",
    ),
    "claim_true": ("who", *_ROLE),
    "counterclaim": ("claimants", *_ROLE),
    "result_wolves": ("winners", "days"),
    "result_village": ("winners", "days"),
    "result_lovers": ("winners", "days"),
    "result_white_wolf": ("winners", "days"),
    "result_nobody": ("winners", "days"),
    "reveal": ("reveal",),
}
# The games whose words live in a module of their own; Werewolf's are in `Teller` itself.
GAME_TELLERS = {"liars_deck": tell_liars_deck, "civ": tell_civ}
PLAIN_VILLAGERS = {
    "en": "plus the plain villagers {names}",
    "de": "dazu die einfachen Dorfbewohner {names}",
}


@cache
def templates(game: str, lang: str) -> dict[str, Any]:
    path = resources.files("arena.chronicle").joinpath(f"templates/{game}.{lang}.yaml")
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def nth(n: int, lang: str) -> str:
    words = NTH[lang]
    return words[n - 1] if 1 <= n <= len(words) else (f"{n}th" if lang == "en" else f"{n}.")


def listing(items: list[str], lang: str) -> str:
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + (" and " if lang == "en" else " und ") + items[-1]


def role_words(role: str | None, lang: str) -> dict[str, str]:
    """A role as a bare noun, with its definite and indefinite article (nominative)."""
    if role is None or role not in load_roles():
        return {"": "", "the": "", "a": "", "acc": ""}
    if lang == "de":
        noun = load_roles()[role].name
        definite, indefinite = DE_ARTICLES.get(role, ("der", "ein"))
        accusative = "einen" if definite == "der" else indefinite  # only "der" words change
        return {
            "": noun,
            "the": f"{definite} {noun}",
            "a": f"{indefinite} {noun}",
            "acc": f"{accusative} {noun}",
        }
    noun = role.replace("_", " ").title()
    the = noun if role == "cupid" else f"the {noun}"
    a = f"{'an' if noun[0] in 'AEIOU' else 'a'} {noun}"
    return {"": noun, "the": the, "a": a, "acc": a}


class Teller:
    """Everything needed to turn facts into sentences of one style and language."""

    def __init__(self, digest: Digest, style: str, lang: str, names: Mapping[str, str]):
        self.digest, self.style, self.lang, self.names = digest, style, lang, names
        self.tpl = templates(digest.game, lang)[style]
        self.rng = random.Random(f"{digest.seed}/{style}/{lang}")
        self.used: set[str] = set()
        self.quoted: set[str] = set()

    def who(self, seat: str | None) -> str:
        return (
            self.names.get(seat, seat) if seat else ("niemand" if self.lang == "de" else "nobody")
        )

    def quote(self, text: str) -> str | None:
        """A quote with display names instead of seat ids and no broken characters.

        None for a quote that says too little (a stock "I have nothing to add") or that was
        already used: the story quotes what is worth quoting, once.
        """
        text = re.sub(r"(?<=\w)�(?=\w)", "'", text).replace("�", "-")
        text = SEAT.sub(lambda m: self.who(m.group(0).lower()), text).replace('"', "'")
        if len(text.split()) < MIN_QUOTE_WORDS or text in self.quoted:
            return None
        self.quoted.add(text)
        return text

    @staticmethod
    def bare(quote: str) -> str:
        """The quote without its closing full stop, for a template that goes on after it."""
        return re.sub(r"[.!?]+$", "", quote)

    def role(self, prefix: str, role: str | None) -> dict[str, str]:
        words = role_words(role, self.lang)
        base = prefix or "role"
        return {
            base: words[""],
            f"{base}_the": words["the"],
            f"{base}_a": words["a"],
            f"{base}_acc": words["acc"],
        }

    def pick(self, kind: str, fields: dict[str, Any]) -> str:
        """A variant of `kind` whose sentences have not been told yet.

        A variant is judged sentence by sentence, so a stock opener ("What a save!") is not
        used twice either; when every variant repeats one, the repeated sentence is left out.
        """
        variants = self.tpl["kinds"][kind]
        order = list(range(len(variants)))
        self.rng.shuffle(order)
        options = []
        for rank, i in enumerate(order):
            text = variants[i].format(**fields)
            parts = SENTENCES.split(text)
            options.append((sum(p in self.used for p in parts), rank, text, parts))
        _, _, text, parts = min(options)
        fresh = [p for p in parts if p not in self.used]
        if fresh and len(fresh) < len(parts):
            text = " ".join(fresh)
        elif not fresh:  # every variant has been told: mark the repeat instead of echoing it
            last = parts[-1]  # the sentence with the facts; a stock opener would repeat as it is
            text = next(
                (
                    c
                    for prefix in self.tpl.get("again", [])
                    if (c := f"{prefix} {last}") not in self.used
                ),
                text,
            )
            parts = SENTENCES.split(text)
        self.used.update(parts)
        return text

    # --- one fact -> (template kind, fields) -------------------------------------------

    def fields_of(self, fact: Fact) -> tuple[str, dict[str, Any]] | None:
        if teller := GAME_TELLERS.get(self.digest.game):
            return teller.fields_of(self, fact)
        d, who, lang = fact.data, self.who, self.lang
        match fact.kind:
            case "cast":
                return "cast", self._cast(d)
            case "lovers":
                return "lovers", {
                    "a": who(d["pair"][0]),
                    "b": who(d["pair"][1]),
                    "by": who(d["by"]),
                }
            case "night_falls" | "day_breaks":
                n = d["n"]
                words = {
                    "n": n,
                    "nth": nth(n, lang),
                    "Nth": nth(n, lang).capitalize(),
                    "alive": d["alive"],
                }
                return fact.kind, words
            case "wolf_plan":
                quote = self.quote(d["quote"])
                return ("wolf_plan", self._quoted({"who": who(d["who"])}, quote)) if quote else None
            case "wolf_target":
                return "wolf_target", {"target": who(d["target"])}
            case "wolf_missed":
                return f"wolf_missed_{d['saved_by'] or 'unknown'}", {"target": who(d["target"])}
            case "seer_look":
                kind = "seer_found_wolf" if d["wolf"] else "seer_found_village"
                return kind, {
                    "seer": who(d["seer"]),
                    "target": who(d["target"]),
                    **self.role("", d["role"]),
                }
            case "witch_heal" | "witch_poison":
                return fact.kind, {"witch": who(d["witch"]), "target": who(d["target"])}
            case "night_quiet":
                return "night_quiet", {}
            case "death":
                kind = {
                    "wolves": "death_wolves",
                    "poison": "death_poison",
                    "grief": "death_grief",
                }.get(d["cause"], "death_other")
                cause = CAUSES[lang].get(d["cause"], (d["cause"] or "").replace("_", " "))
                return kind, {
                    "player": who(d["player"]),
                    "cause": cause,
                    **self.role("", d["role"]),
                }
            case "hunter_shot":
                return "hunter_shot", {"hunter": who(d["hunter"]), "target": who(d["target"])}
            case "captain":
                return "captain", {"player": who(d["player"]), "votes": d["votes"]}
            case "vote_reason":
                quote = self.quote(d["quote"])
                if not quote:
                    return None
                fields = {"who": who(d["who"]), "target": who(d["target"])}
                return "vote_reason", self._quoted(fields, quote)
            case "speech":
                quote = self.quote(d["quote"]) if d["focus"] else None
                if not quote:
                    return None
                if d["who"] == d["focus"]:
                    return "speech_own", self._quoted({"who": who(d["who"])}, quote)
                fields = {"who": who(d["who"]), "focus": who(d["focus"])}
                return "speech_accuser", self._quoted(fields, quote)
            case "tally":
                tally = ", ".join(f"{who(t)} {n}" for t, n in d["counts"])
                kind = "tally_decided" if d["executed"] else "tally_none"
                return kind, {"tally": tally, "executed": who(d["executed"]), "votes": 0}
            case "execution":
                kind = {"village": "execution_wrong", "wolves": "execution_wolf"}.get(
                    d["team"], "execution_other"
                )
                return kind, {
                    "player": who(d["player"]),
                    "votes": d["votes"],
                    **self.role("", d["role"]),
                }
            case "no_execution":
                return "no_execution", {}
            case "claim_lie":
                return "claim_lie", {
                    "who": who(d["who"]),
                    **self.role("claimed", d["claimed"]),
                    **self.role("actual", d["actual"]),
                }
            case "claim_true":
                return "claim_true", {"who": who(d["who"]), **self.role("", d["claimed"])}
            case "counterclaim":
                return "counterclaim", {
                    "claimants": listing([who(s) for s in d["claimants"]], lang),
                    **self.role("", d["role"]),
                }
            case "result":
                names = listing([who(s) for s in d["winners"]], lang)
                return f"result_{d['winner']}", {"winners": names, "days": d.get("days", 0)}
            case "reveal":
                shown = [
                    f"{who(p['seat'])} ({role_words(p['role'], lang)['']})" for p in d["players"]
                ]
                return "reveal", {"reveal": ", ".join(shown)}
        return None

    def _quoted(self, fields: dict[str, Any], quote: str) -> dict[str, Any]:
        return {**fields, "quote": quote, "quote_bare": self.bare(quote)}

    def _cast(self, d: dict[str, Any]) -> dict[str, Any]:
        special, plain = [], []
        for player in d["players"]:
            (plain if player["role"] == "villager" else special).append(player)
        parts = [
            f"{self.who(p['seat'])}, {role_words(p['role'], self.lang)['the']}" for p in special
        ]
        if plain:
            names = listing([self.who(p["seat"]) for p in plain], self.lang)
            parts.append(PLAIN_VILLAGERS[self.lang].format(names=names))
        return {"cast": "; ".join(parts), "count": len(d["players"])}


def _layout(sentences: list[str], layout: Mapping[str, Any]) -> str:
    prefix = layout["prefix"]
    lines = [f"{prefix}{s}" for s in sentences]
    size = layout["paragraph"]
    if size:
        paragraphs = [lines[i : i + size] for i in range(0, len(lines), size)]
        return "\n\n".join(layout["joiner"].join(p) for p in paragraphs)
    return layout["joiner"].join(lines)


def _title(teller: Teller, kind: str, number: int) -> str:
    return teller.tpl["chapters"][kind].format(
        n=number, nth=nth(number, teller.lang), Nth=nth(number, teller.lang).capitalize()
    )


def chapters(teller: Teller) -> list[dict[str, Any]]:
    """The chapters of the story: title, kind, the first log position and the text."""
    out = []
    for section in teller.digest.sections:
        sentences = []
        for fact in section.facts:
            resolved = teller.fields_of(fact)
            if resolved:
                text = teller.pick(*resolved)
                finish = getattr(GAME_TELLERS.get(teller.digest.game), "finish", None)
                sentences.append(finish(text, teller.lang) if finish else text)
        if not sentences:
            continue
        seq = min((f.data["seq"] for f in section.facts if "seq" in f.data), default=None)
        out.append(
            {
                "number": len(out) + 1,
                "kind": section.kind,
                "title": _title(teller, section.kind, section.number),
                "text": _layout(sentences, teller.tpl["layout"]),
                "seq": seq,
            }
        )
    return out


def _euros(micro_eur: int) -> str:
    return f"EUR {micro_eur / 1_000_000:.4f}"


def glance(teller: Teller, cost_micro_eur: int | None) -> list[dict[str, str]]:
    """The "At a glance" box: a label and a value per item."""
    tpl, who, lang = teller.tpl, teller.who, teller.lang
    items = []
    for fact in teller.digest.glance:
        d = fact.data
        if game_teller := GAME_TELLERS.get(teller.digest.game):
            if (value := game_teller.glance_value(teller, fact)) is not None:
                items.append({"label": tpl["glance_labels"][fact.kind], "value": value})
            continue
        match fact.kind:
            case "winner":
                side = SIDES[lang][d["winner"]]
                winners = listing([who(s) for s in d["winners"]], lang)
                value = f"{side} ({winners})" if winners else side
            case "length":
                value = tpl["glance_values"]["length"].format(days=d["days"])
            case "turning_point":
                value = tpl["turning_points"][d["type"]].format(
                    n=d.get("n", 0),
                    player=who(d.get("player")),
                    hunter=who(d.get("hunter")),
                    target=who(d.get("target")),
                    who=who(d.get("who")),
                    votes=d.get("votes", 0),
                    **teller.role("", d.get("role")),
                )
            case "accurate_voter":
                value = tpl["glance_values"]["accurate_voter"].format(
                    who=who(d["who"]), right=d["right"], of=d["of"]
                )
            case "deceptive":
                notes = tpl["deceptive_notes"]
                note = notes["survived" if d["survived"] else "fell"].format(days=d["days"])
                if d["lies"]:
                    note += notes["lies"].format(lies=d["lies"])
                value = tpl["glance_values"]["deceptive"].format(
                    who=who(d["who"]), deceptive_note=note
                )
            case _:
                continue
        items.append({"label": tpl["glance_labels"][fact.kind], "value": value})
    if cost_micro_eur is not None:
        items.append(
            {
                "label": tpl["glance_labels"]["cost"],
                "value": tpl["glance_values"]["cost"].format(cost=_euros(cost_micro_eur)),
            }
        )
    return items


KEY_KINDS = {
    "werewolf": ("death", "execution", "hunter_shot", "claim_lie", "captain", "wolf_missed"),
    "liars_deck": ("reveal", "trigger", "eliminated", "duel", "devil_shots", "lie_big"),
    "civ": ("conquest", "battle", "war", "treaty", "broken", "event"),
}
FIELDS_BY_GAME = {
    "werewolf": FIELDS,
    "liars_deck": tell_liars_deck.FIELDS,
    "civ": tell_civ.FIELDS,
}


def key_moments(digest: Digest) -> list[dict[str, Any]]:
    """What a report can jump to: where a key fact happened (`seq` in the whole log)."""
    out = []
    for section in digest.sections:
        for fact in section.facts:
            if fact.kind in KEY_KINDS[digest.game]:
                d = fact.data
                keys = ("player", "who", "hunter", "target", "caller", "a", "b")
                keys += ("taker", "loser", "attacker", "defender", "by", "on", "other")
                named = [d[k] for k in keys if d.get(k)] + list(d.get("players", []))
                named += list(d.get("nations", []))
                players = [p for p in named if p in digest.seats]  # not the barbarians
                out.append(
                    {
                        "seq": d["seq"],
                        "kind": fact.kind,
                        "players": players,
                        "phase": section.kind,
                        "number": section.number,
                    }
                )
    return out
