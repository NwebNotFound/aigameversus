"""The narrator's words, from templates. Works without any model.

The plugin emits a public `narration` event for every moment the narrator
speaks: its `key`, the facts (`data`) and the template `text`. A game master
with a model may retell it (`arena/gamemaster/narrator.py`); the facts and the
template stay in the log either way.
"""

from collections.abc import Mapping
from typing import Any

from games.werewolf.selection import load_roles

LANGUAGES = ("de", "en")

TEMPLATES: dict[str, dict[str, str]] = {
    "de": {
        "night_falls": "Nacht {night} bricht herein. Das Dorf schläft.",
        "morning_quiet": "Der Morgen graut. Niemand ist in dieser Nacht gestorben.",
        "morning_deaths": "Der Morgen graut. Tot aufgefunden: {deaths}.",
        "captain_elected": "{player} ist jetzt Hauptmann des Dorfes.",
        "captain_passed": "{player} übernimmt das Amt des Hauptmanns.",
        "execution": "Das Dorf hat entschieden: {player} wird hingerichtet. {player} war {role}.",
        "no_execution": "Das Dorf ist sich nicht einig. Heute stirbt niemand.",
        "game_over": "Das Spiel ist aus. {winner}",
        "grief": "{player} stirbt aus Kummer um {lover}.",
        "idiot_spared": "{player} ist der Dorfdepp und überlebt, darf aber nicht mehr abstimmen.",
        "scapegoat": "Gleichstand. Der Sündenbock {player} muss sterben.",
        "powers_lost": (
            "Das Dorf hat seinen Ältesten {player} getötet. "
            "Alle Sonderrollen des Dorfes verlieren ihre Kräfte."
        ),
    },
    "en": {
        "night_falls": "Night {night} falls. The village sleeps.",
        "morning_quiet": "Dawn breaks. Nobody died tonight.",
        "morning_deaths": "Dawn breaks. Found dead: {deaths}.",
        "captain_elected": "{player} is now the village captain.",
        "captain_passed": "{player} takes over as captain.",
        "execution": "The village has decided: {player} is executed. {player} was {role}.",
        "no_execution": "The village cannot agree. Nobody dies today.",
        "game_over": "The game is over. {winner}",
        "grief": "{player} dies of grief for {lover}.",
        "idiot_spared": "{player} is the Village Idiot and survives, but may no longer vote.",
        "scapegoat": "A tie. The scapegoat {player} must die.",
        "powers_lost": (
            "The village killed its Elder {player}. All village special roles lose their powers."
        ),
    },
}

WINNERS = {
    "de": {
        "village": "Das Dorf hat gewonnen.",
        "wolves": "Die Werwölfe haben gewonnen.",
        "nobody": "Niemand hat überlebt.",
        "lovers": "Das Liebespaar hat gewonnen.",
    },
    "en": {
        "village": "The village wins.",
        "wolves": "The werewolves win.",
        "nobody": "Nobody survived.",
        "lovers": "The lovers win.",
    },
}


def role_name(role_id: str) -> str:
    return load_roles()[role_id].name


def narrate(key: str, data: Mapping[str, Any], language: str) -> str:
    """The template text for one narrator moment."""
    words = dict(data)
    if "deaths" in words:
        words["deaths"] = ", ".join(
            f"{d['player']} ({role_name(d['role'])})" for d in data["deaths"]
        )
    if "role" in words:
        words["role"] = role_name(words["role"])
    if "winner" in words:
        words["winner"] = WINNERS[language].get(words["winner"], str(words["winner"]))
    return TEMPLATES[language][key].format(**words)
