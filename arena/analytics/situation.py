# ruff: noqa: E501  (lines of prose)
"""How is the game going? A few facts and short sentences, in English and German, per game.

Built from the same log as the rest of the analytics, so a spoiler-free viewer gets
sentences from public events only. Facts that need hidden information (the teams
in Werewolf) appear only with spoilers. Sentences name the seats by their display
names; the words for cards, roles and deaths come from the transcript and the
chronicle, so a card reads the same everywhere.
"""

from collections import Counter
from collections.abc import Callable, Mapping
from typing import Any

from arena.chronicle.text import CAUSES
from arena.engine.types import Event
from arena.transcript.liars_deck import TITLE
from games.liars_deck.variants import load_variants
from games.poker.plugin import DEFAULTS as POKER_DEFAULTS
from games.werewolf.selection import load_roles

Log = list[tuple[int, Event]]
Names = Mapping[str, str]
SHORT_STACK_BIG_BLINDS = 10  # a Poker stack below this many big blinds counts as short


def situation(game: str, log: Log, spoilers: bool, names: Names) -> dict[str, Any] | None:
    """{"facts": {...}, "lines": {"en": [...], "de": [...]}}; None for a game without one yet."""
    build = BUILDERS.get(game)
    if build is None:
        return None
    facts = build(log, spoilers)
    lines = {lang: WRITERS[game](facts, lang, _namer(names)) for lang in ("en", "de")}
    return {"facts": facts, "lines": lines}


def _namer(names: Names) -> Callable[[str], str]:
    return lambda seat: names.get(seat, seat)


def _pick(lang: str, en: str, de: str) -> str:
    return en if lang == "en" else de


def _number(value: int, lang: str) -> str:
    text = f"{value:,}"
    return text if lang == "en" else text.replace(",", ".")


def _percent(share: float) -> str:
    return f"{round(share * 100)} %"


def _listing(items: list[str], lang: str) -> str:
    if len(items) <= 1:
        return "".join(items)
    return f"{', '.join(items[:-1])} {_pick(lang, 'and', 'und')} {items[-1]}"


# --- Liar's Deck ------------------------------------------------------------


def _liars_facts(log: Log, spoilers: bool) -> dict[str, Any]:
    events = [event for _, event in log]
    start = next((e for e in events if e.type == "match_started"), None)
    variant = ((start.data.get("settings") or {}) if start else {}).get("variant", "base")
    revolver = load_variants().get(variant, load_variants()["base"]).revolver
    pulls: Counter[str] = Counter()
    out: list[str] = []
    facts: dict[str, Any] = {
        "round": None,
        "table_card": None,
        "turn": None,
        "alive": list(start.data.get("players", [])) if start else [],
        "cards_left": {},
        "last_call": None,
        "winner": None,
    }
    for event in events:
        data = event.data
        if event.type == "round_started":
            facts.update(round=data["round"], table_card=data["table_card"], turn=data["starter"])
            facts["alive"] = list(data["players"])
            facts["cards_left"] = {p: data["hand_size"] for p in data["players"]}
        elif event.type == "cards_played" and data["player"] in facts["cards_left"]:
            facts["cards_left"][data["player"]] -= data["count"]
        elif event.type == "turn_passed":
            facts["turn"] = data["player"]
        elif event.type == "liar_called":
            facts["last_call"] = {
                "caller": data["caller"],
                "target": data["target"],
                "honest": None,
                "shooters": [],
                "survived": {},
            }
        elif event.type == "cards_revealed" and facts["last_call"]:
            facts["last_call"]["honest"] = data["honest"]
        elif event.type == "shooters_chosen" and facts["last_call"]:
            facts["last_call"]["shooters"] = list(data["players"])
        elif event.type == "trigger_pulled":
            pulls[data["player"]] += 1
            if facts["last_call"]:
                facts["last_call"]["survived"][data["player"]] = not data["live"]
        elif event.type == "players_eliminated":
            out.extend(data["players"])
            facts["alive"] = [p for p in facts["alive"] if p not in data["players"]]
        elif event.type == "match_over":
            facts["winner"] = data.get("winner")
    # The chance that a player's next pull fires: public, from the variant and the pulls.
    facts["risk"] = {
        p: min(1.0, revolver.live / max(revolver.chambers - pulls[p], 1)) for p in facts["alive"]
    }
    facts["pulls"] = {p: pulls[p] for p in facts["alive"]}
    facts["out"] = out
    facts["closest"] = (
        max(facts["alive"], key=lambda p: (facts["risk"][p], -facts["alive"].index(p)))
        if facts["alive"] and any(pulls[p] for p in facts["alive"])
        else None
    )
    return facts


def _liars_lines(facts: dict[str, Any], lang: str, name: Callable[[str], str]) -> list[str]:
    if facts["winner"]:
        return [
            _pick(
                lang,
                f"{name(facts['winner'])} wins the match.",
                f"{name(facts['winner'])} gewinnt die Partie.",
            )
        ]
    if facts["round"] is None:
        return [_pick(lang, "The match is about to start.", "Die Partie beginnt gleich.")]
    card = TITLE[lang].get(facts["table_card"], facts["table_card"])
    lines = [
        _pick(
            lang,
            f"Round {facts['round']} · table card: {card}",
            f"Runde {facts['round']} · Tischkarte: {card}",
        )
        + (
            _pick(lang, f" · {name(facts['turn'])} to play.", f" · {name(facts['turn'])} ist dran.")
            if facts["turn"]
            else "."
        )
    ]
    left = [f"{name(p)} {n}" for p, n in facts["cards_left"].items() if p in facts["alive"]]
    if left:
        lines.append(_pick(lang, "Cards left: ", "Karten übrig: ") + ", ".join(left) + ".")
    if facts["closest"]:
        p = facts["closest"]
        chance = _percent(facts["risk"][p])
        lines.append(
            _pick(
                lang,
                f"Closest to elimination: {name(p)}, {facts['pulls'][p]} pulls survived; the next one fires with {chance}.",
                f"Am nächsten am Ausscheiden: {name(p)}, {facts['pulls'][p]} Abzüge überlebt; der nächste geht mit {chance} los.",
            )
        )
    call = facts["last_call"]
    if call:
        caller, target = name(call["caller"]), name(call["target"])
        text = _pick(
            lang,
            f"Last call: {caller} called {target} a liar",
            f"Letzter Ruf: {caller} nannte {target} einen Lügner",
        )
        if call["honest"] is not None:
            text += _pick(
                lang,
                f", and {target} was {'honest' if call['honest'] else 'lying'}",
                f", und {target} hat {'die Wahrheit gesagt' if call['honest'] else 'gelogen'}",
            )
        text += "."
        for shooter, survived in call["survived"].items():
            text += " " + _pick(
                lang,
                f"{name(shooter)} pulled the trigger and {'survived' if survived else 'is out'}.",
                f"{name(shooter)} drückte ab und {'überlebte' if survived else 'ist raus'}.",
            )
        lines.append(text)
    return lines


# --- Poker ------------------------------------------------------------------


def _poker_facts(log: Log, spoilers: bool) -> dict[str, Any]:
    events = [event for _, event in log]
    start = next((e for e in events if e.type == "match_started"), None)
    players = list(start.data.get("players", [])) if start else []
    settings = (start.data.get("settings") or {}) if start else {}
    stacks = {p: settings.get("starting_stack", POKER_DEFAULTS["starting_stack"]) for p in players}
    facts: dict[str, Any] = {
        "hand": None,
        "street": None,
        "pot": 0,
        "big_blind": None,
        "in_hand": [],
        "out": [],
        "biggest_pot": None,
        "winner": None,
        "over": False,
    }
    for event in events:
        data = event.data
        if event.type == "hand_started":
            facts.update(hand=data["hand"], street=None, pot=0, big_blind=data["big_blind"])
            facts["in_hand"] = list(data["players"])
        elif event.type == "blind_posted":
            stacks[data["player"]] -= data["amount"]
            facts["pot"] += data["amount"]
        elif event.type == "street_started":
            facts["street"] = data["street"]
        elif event.type == "bet_action":
            stacks[data["player"]] -= data["added"]
            facts["pot"] += data["added"]
            if data["kind"] == "fold" and data["player"] in facts["in_hand"]:
                facts["in_hand"].remove(data["player"])
        elif event.type == "pot_awarded":
            for player, share in data["shares"].items():
                stacks[player] += share
            facts["pot"] -= data["amount"]
            biggest = facts["biggest_pot"]
            if biggest is None or data["amount"] > biggest["amount"]:
                facts["biggest_pot"] = {
                    "amount": data["amount"],
                    "to": sorted(data["shares"]),
                    "hand": facts["hand"],
                }
        elif event.type == "players_eliminated":
            facts["out"].extend(data["players"])
        elif event.type == "match_over":
            facts.update(winner=data.get("winner"), over=True)
    playing = [p for p in players if p not in facts["out"]]
    facts["stacks"] = {p: stacks[p] for p in playing}
    facts["chip_leader"] = (
        max(playing, key=lambda p: (stacks[p], -players.index(p))) if playing else None
    )
    facts["all_in"] = [
        p for p in facts["in_hand"] if p in playing and stacks[p] == 0 and facts["pot"] > 0
    ]
    bb = facts["big_blind"]
    facts["short"] = [p for p in playing if bb and 0 < stacks[p] < SHORT_STACK_BIG_BLINDS * bb]
    return facts


STREETS = {
    "en": {"preflop": "before the flop", "flop": "flop", "turn": "turn", "river": "river"},
    "de": {"preflop": "vor dem Flop", "flop": "Flop", "turn": "Turn", "river": "River"},
}


def _poker_lines(facts: dict[str, Any], lang: str, name: Callable[[str], str]) -> list[str]:
    n = lambda value: _number(value, lang)  # noqa: E731
    if facts["winner"]:
        return [
            _pick(
                lang,
                f"{name(facts['winner'])} wins the tournament.",
                f"{name(facts['winner'])} gewinnt das Turnier.",
            )
        ]
    if facts["hand"] is None:
        return [
            _pick(
                lang, "The first hand is about to be dealt.", "Die erste Hand wird gleich gegeben."
            )
        ]
    head = f"{_pick(lang, 'Hand', 'Hand')} {facts['hand']}"
    if facts["street"]:
        head += f" · {STREETS[lang].get(facts['street'], facts['street'])}"
    lines = [f"{head} · {_pick(lang, 'pot', 'Pot')} {n(facts['pot'])}."]
    if facts["over"]:
        lines = [
            _pick(
                lang,
                f"Over after hand {facts['hand']}: the hand limit is reached.",
                f"Vorbei nach Hand {facts['hand']}: das Handlimit ist erreicht.",
            )
        ]
    if facts["chip_leader"]:
        leader = facts["chip_leader"]
        lines.append(
            _pick(
                lang,
                f"Chip leader: {name(leader)} with {n(facts['stacks'][leader])}.",
                f"Chipleader: {name(leader)} mit {n(facts['stacks'][leader])}.",
            )
        )
    if facts["all_in"]:
        lines.append(
            _pick(lang, "All in: ", "All-in: ")
            + _listing([name(p) for p in facts["all_in"]], lang)
            + "."
        )
    short = [
        f"{name(p)} ({n(facts['stacks'][p])})" for p in facts["short"] if p not in facts["all_in"]
    ]
    if short:
        lines.append(
            _pick(
                lang,
                f"Short stack, under {SHORT_STACK_BIG_BLINDS} big blinds: ",
                f"Kurzer Stack, unter {SHORT_STACK_BIG_BLINDS} Big Blinds: ",
            )
            + ", ".join(short)
            + "."
        )
    if facts["biggest_pot"]:
        pot = facts["biggest_pot"]
        to = _listing([name(p) for p in pot["to"]], lang)
        lines.append(
            _pick(
                lang,
                f"Biggest pot so far: {n(pot['amount'])} to {to} in hand {pot['hand']}.",
                f"Größter Pot bisher: {n(pot['amount'])} an {to} in Hand {pot['hand']}.",
            )
        )
    return lines


# --- Werewolf ---------------------------------------------------------------


def _werewolf_facts(log: Log, spoilers: bool) -> dict[str, Any]:
    events = [event for _, event in log]
    start = next((e for e in events if e.type == "match_started"), None)
    players = list(start.data.get("players", [])) if start else []
    facts: dict[str, Any] = {
        "phase": None,
        "number": None,
        "players": len(players),
        "alive": list(players),
        "votes": {},
        "last_death": None,
        "winner": None,
        "teams": None,
    }
    roles: dict[str, str] = {}
    wolves: set[str] = set()  # turned into wolves during the match
    for event in events:
        data = event.data
        if event.type == "night_started":
            facts.update(phase="night", number=data["night"])
        elif event.type == "morning_started":
            facts.update(phase="day", number=data["night"], votes={})
        elif event.type == "day_started":
            facts.update(phase="day", number=data["day"], votes={})
        elif event.type == "vote_cast":
            if data["target"] is not None:  # None: the player abstained
                facts["votes"][data["target"]] = facts["votes"].get(data["target"], 0) + 1
        elif event.type == "player_died":
            if data["player"] in facts["alive"]:
                facts["alive"].remove(data["player"])
            facts["last_death"] = {
                "player": data["player"],
                "cause": data.get("cause"),
                "role": data.get("role"),
            }
        elif event.type == "role_assigned":
            roles[data["player"]] = data["role"]
        elif event.type in ("infected", "joined_pack") and "player" in data:
            wolves.add(data["player"])
        elif event.type == "game_over":
            facts["winner"] = data.get("winner")
    if spoilers and roles:
        known = load_roles()
        teams = Counter(
            "wolves" if p in wolves else known[roles[p]].team for p in facts["alive"] if p in roles
        )
        facts["teams"] = dict(teams)
    facts["votes"] = dict(sorted(facts["votes"].items(), key=lambda item: -item[1]))
    return facts


TEAMS = {
    "en": {"village": "village", "wolves": "wolves", "solo": "on their own"},
    "de": {"village": "Dorf", "wolves": "Werwölfe", "solo": "allein"},
}
WINNERS = {
    "en": {
        "wolves": "The werewolves win.",
        "village": "The village wins.",
        "lovers": "The lovers win.",
    },
    "de": {
        "wolves": "Die Werwölfe gewinnen.",
        "village": "Das Dorf gewinnt.",
        "lovers": "Das Liebespaar gewinnt.",
    },
}


def _role_word(role: str, lang: str) -> str:
    return (
        load_roles()[role].name if lang == "de" and role in load_roles() else role.replace("_", " ")
    )


def _werewolf_lines(facts: dict[str, Any], lang: str, name: Callable[[str], str]) -> list[str]:
    if facts["winner"]:
        return [
            WINNERS[lang].get(
                facts["winner"], _pick(lang, "The game is over.", "Das Spiel ist aus.")
            )
        ]
    if facts["phase"] is None:
        return [_pick(lang, "The village is about to fall asleep.", "Das Dorf schläft gleich ein.")]
    when = _pick(
        lang,
        "Night" if facts["phase"] == "night" else "Day",
        "Nacht" if facts["phase"] == "night" else "Tag",
    )
    alive, total = len(facts["alive"]), facts["players"]
    lines = [
        f"{when} {facts['number']} · "
        + _pick(lang, f"{alive} of {total} alive.", f"{alive} von {total} leben.")
    ]
    if facts["teams"]:
        parts = [
            f"{count} {TEAMS[lang].get(team, team)}"
            for team, count in sorted(facts["teams"].items())
        ]
        lines.append(_pick(lang, "Alive by team: ", "Lebend nach Team: ") + ", ".join(parts) + ".")
    if facts["phase"] == "day" and facts["votes"]:
        votes = [f"{name(target)} {count}" for target, count in facts["votes"].items()]
        lines.append(_pick(lang, "Votes today: ", "Stimmen heute: ") + ", ".join(votes) + ".")
    death = facts["last_death"]
    if death:
        cause = CAUSES[lang].get(death["cause"], (death["cause"] or "").replace("_", " "))
        role = f", {_role_word(death['role'], lang)}" if death["role"] else ""
        lines.append(
            _pick(lang, "Last death: ", "Zuletzt gestorben: ")
            + f"{name(death['player'])}{role}, {cause}."
        )
    return lines


BUILDERS: dict[str, Callable[[Log, bool], dict[str, Any]]] = {
    "liars_deck": _liars_facts,
    "poker": _poker_facts,
    "werewolf": _werewolf_facts,
}
WRITERS = {"liars_deck": _liars_lines, "poker": _poker_lines, "werewolf": _werewolf_lines}
