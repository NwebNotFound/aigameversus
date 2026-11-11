# ruff: noqa: E501  (lines of prose)
"""The game master's voice: dramatic lines for a game's narration, in English and German.

A game emits `narration` events with a key, the facts and a plain template text
(`games/werewolf/narrator.py`). This turns each into a livelier line for the
watch screen: several variants per moment, the variant chosen from the event's
place in the log (so a replay reads the same and no hidden seed is needed), the
players by their display names. It only says what the facts say.

The template voice is the default and costs nothing. `Voice` is the hook for a
model (`arena/gamemaster/narrator.py`, `retell`): it gets the same facts, and the
template line stands whenever the model fails. No model is called by default.
"""

import zlib
from collections.abc import Callable, Mapping
from typing import Any, Protocol

from arena.engine.types import Event
from games.werewolf.selection import load_roles

Name = Callable[[str], str]

LINES: dict[str, dict[str, list[str]]] = {
    "night_falls": {
        "en": [
            "Night {night}. The lamps go out one by one, and somewhere a door creaks.",
            "Night {night} settles over the village like a held breath.",
            "The moon rises over night {night}. Not everyone will see the dawn.",
            "Night {night}. The village sleeps; the wolves do not.",
        ],
        "de": [
            "Nacht {night}. Eine Lampe nach der anderen erlischt, irgendwo knarrt eine Tür.",
            "Nacht {night} legt sich über das Dorf wie ein angehaltener Atem.",
            "Der Mond steigt über Nacht {night}. Nicht alle werden den Morgen sehen.",
            "Nacht {night}. Das Dorf schläft, die Wölfe nicht.",
        ],
    },
    "morning_quiet": {
        "en": [
            "Dawn, and every door opens. Nobody died tonight.",
            "The sun comes up on a village still whole. A quiet night, for once.",
            "Morning. Everyone is counted, everyone is there. Who stopped the wolves?",
        ],
        "de": [
            "Morgengrauen, und jede Tür geht auf. Niemand ist in dieser Nacht gestorben.",
            "Die Sonne geht über einem vollständigen Dorf auf. Eine ruhige Nacht, ausnahmsweise.",
            "Morgen. Alle gezählt, alle da. Wer hat die Wölfe aufgehalten?",
        ],
    },
    "morning_deaths": {
        "en": [
            "Dawn brings bad news: {deaths} did not live through the night.",
            "The village wakes to a terrible sight. {deaths}: gone.",
            "Morning light falls on {deaths}. The night took its toll.",
        ],
        "de": [
            "Der Morgen bringt schlechte Nachricht. Tot aufgefunden: {deaths}.",
            "Das Dorf erwacht vor einem schrecklichen Anblick. {deaths}: tot.",
            "Das Morgenlicht fällt auf {deaths}. Die Nacht hat ihren Preis gefordert.",
        ],
    },
    "captain_elected": {
        "en": [
            "The village puts its trust in {player}: the new captain.",
            "{player} takes the captain's sash. Every vote of theirs now weighs double.",
        ],
        "de": [
            "Das Dorf vertraut {player}: der neue Hauptmann.",
            "{player} nimmt die Schärpe des Hauptmanns. Jede Stimme zählt jetzt doppelt.",
        ],
    },
    "captain_passed": {
        "en": [
            "With the last breath, the captaincy passes to {player}.",
            "{player} inherits the captain's sash.",
        ],
        "de": [
            "Mit dem letzten Atemzug geht das Amt an {player}.",
            "{player} erbt die Schärpe des Hauptmanns.",
        ],
    },
    "execution": {
        "en": [
            "The votes are counted. {player} walks to the gallows and is revealed: {role}.",
            "The village has spoken. {player} is executed, and the truth comes out: {role}.",
            "No more words. {player} dies by the village's hand, {role} to the end.",
        ],
        "de": [
            "Die Stimmen sind gezählt. {player} geht zum Galgen und wird enthüllt: {role}.",
            "Das Dorf hat gesprochen. {player} wird hingerichtet, und die Wahrheit kommt ans Licht: {role}.",
            "Keine Worte mehr. {player} stirbt durch die Hand des Dorfes, {role} bis zuletzt.",
        ],
    },
    "no_execution": {
        "en": [
            "The village argues until sunset and cannot agree. Nobody hangs today.",
            "No majority. The rope stays coiled tonight.",
        ],
        "de": [
            "Das Dorf streitet bis Sonnenuntergang und wird sich nicht einig. Heute hängt niemand.",
            "Keine Mehrheit. Der Strick bleibt heute aufgerollt.",
        ],
    },
    "grief": {
        "en": ["{player} cannot live without {lover} and follows them into death."],
        "de": ["{player} kann ohne {lover} nicht leben und folgt in den Tod."],
    },
    "bear_growl": {
        "en": ["The Bear Tamer's bear growls low. A wolf sits right beside its master."],
        "de": ["Der Bär des Bärenführers knurrt leise. Direkt neben seinem Herrn sitzt ein Wolf."],
    },
    "raven_mark": {
        "en": ["A raven feather lies on {player}'s doorstep: two votes against {player} today."],
        "de": ["Eine Rabenfeder liegt vor {player}s Tür: zwei Stimmen gegen {player} heute."],
    },
    "idiot_spared": {
        "en": [
            "The noose tightens, then loosens: {player} is the Village Idiot. Spared, but silenced at the vote."
        ],
        "de": [
            "Die Schlinge zieht sich zu, dann lockert sie sich: {player} ist der Dorfdepp. Verschont, aber ohne Stimme."
        ],
    },
    "scapegoat": {
        "en": ["A tie, and the village needs someone to blame. The scapegoat {player} pays."],
        "de": [
            "Gleichstand, und das Dorf braucht einen Schuldigen. Der Sündenbock {player} bezahlt."
        ],
    },
    "powers_lost": {
        "en": ["The village has killed its own Elder, {player}. Every gift of the village fades."],
        "de": [
            "Das Dorf hat seinen eigenen Ältesten getötet, {player}. Jede Gabe des Dorfes erlischt."
        ],
    },
    "game_over": {
        "en": ["It is over. {winner}"],
        "de": ["Es ist vorbei. {winner}"],
    },
}

WINNERS = {
    "en": {
        "village": "The village survives the wolves.",
        "wolves": "The wolves own the village now.",
        "nobody": "Nobody is left to tell the tale.",
        "lovers": "Only the lovers remain, together.",
        "white_wolf": "The White Werewolf stands alone, the last one alive.",
    },
    "de": {
        "village": "Das Dorf übersteht die Wölfe.",
        "wolves": "Das Dorf gehört jetzt den Wölfen.",
        "nobody": "Niemand ist übrig, um davon zu erzählen.",
        "lovers": "Nur das Liebespaar bleibt, gemeinsam.",
        "white_wolf": "Der Weiße Werwolf steht allein, der Letzte am Leben.",
    },
}


def _role(role: str | None, lang: str) -> str:
    if role is None:
        return "?"
    if lang == "de":
        return load_roles()[role].name if role in load_roles() else role
    return f"the {role.replace('_', ' ')}"


def _join(items: list[str], lang: str) -> str:
    if len(items) <= 1:
        return "".join(items)
    return f"{', '.join(items[:-1])} {'and' if lang == 'en' else 'und'} {items[-1]}"


def line(key: str, data: Mapping[str, Any], lang: str, name: Name, pick: int) -> str | None:
    """The dramatic line for one narration moment, or None for a key without lines."""
    variants = LINES.get(key, {}).get(lang)
    if not variants:
        return None
    words: dict[str, Any] = dict(data)
    if "deaths" in data:
        words["deaths"] = _join(
            [f"{name(d['player'])} ({_role(d.get('role'), lang)})" for d in data["deaths"]], lang
        )
    for field in ("player", "lover"):
        if field in data:
            words[field] = name(data[field])
    if "role" in data:
        words["role"] = _role(data["role"], lang)
    if "winner" in data:
        words["winner"] = WINNERS[lang].get(data["winner"], str(data["winner"]))
    return variants[pick % len(variants)].format(**words)


class Voice(Protocol):
    """Speaks one narration moment. The template voice is the default; a model may replace it."""

    def speak(
        self, key: str, data: Mapping[str, Any], lang: str, name: Name, pick: int
    ) -> str | None: ...


class TemplateVoice:
    def speak(
        self, key: str, data: Mapping[str, Any], lang: str, name: Name, pick: int
    ) -> str | None:
        return line(key, data, lang, name, pick)


def narration(
    log: list[tuple[int, Event]], names: Mapping[str, str], voice: Voice | None = None
) -> list[dict[str, Any]]:
    """Every narration event of a log as {seq, key, text{en, de}}; the plain text where a key has no lines."""
    voice = voice or TemplateVoice()
    name = lambda seat: names.get(seat, seat)  # noqa: E731
    out = []
    seen: dict[str, int] = {}
    for seq, event in log:
        if event.type != "narration":
            continue
        key, data = event.data["key"], event.data.get("data") or {}
        # The variant follows the moment and how often it came before: the same match reads the
        # same, and the second night does not open like the first.
        pick = zlib.crc32(key.encode()) + seen.get(key, 0)
        seen[key] = seen.get(key, 0) + 1
        texts = {
            lang: voice.speak(key, data, lang, name, pick) or event.data.get("text", "")
            for lang in ("en", "de")
        }
        out.append({"seq": seq, "key": key, "text": texts})
    return out
