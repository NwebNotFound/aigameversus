# ruff: noqa: E501  (the templates are long lines of prose)
"""Words for the beats: four styles in two languages, from fixed templates.

The text is a pure function of the beats, the style, the language and the names,
so the same log always gives the same chronicle. Every template of a style uses
the same fields for a kind of beat; `FIELDS` lists them, and the tests render
every kind in every style and language.
"""

from collections.abc import Mapping
from typing import Any

from arena.chronicle.beats import Beat

STYLES = ("epic", "news", "sports", "novel")
LANGS = ("en", "de")

# The kinds of beats, in the order of the template tuples below, with their fields.
FIELDS: dict[str, tuple[str, ...]] = {
    "ld_round": ("round", "card", "players"),
    "ld_play": ("player", "count"),
    "ld_call": ("caller", "target"),
    "ld_call_auto": ("caller", "target"),
    "ld_caught": ("caller", "target", "cards", "card"),
    "ld_wrong": ("caller", "target", "cards", "card"),
    "ld_click": ("player", "pull"),
    "ld_bang": ("player",),
    "ld_win": ("winner",),
    "pk_hand": ("hand", "button", "big_blind"),
    "pk_street": ("street", "cards"),
    "pk_raise": ("player", "to"),
    "pk_allin": ("player",),
    "pk_fold": ("player",),
    "pk_showdown": ("hands",),
    "pk_award": ("winners", "amount"),
    "pk_out": ("player",),
    "pk_win": ("winner",),
    "ww_cast": ("cast",),
    "ww_night": ("night",),
    "ww_dawn_quiet": (),
    "ww_death": ("player", "role", "cause"),
    "ww_growl": (),
    "ww_vote": ("executed", "votes"),
    "ww_novote": (),
    "ww_hunter": ("player", "target"),
    "ww_end": ("outcome",),
    "pk_limit": ("leaders",),
}
# pk_limit (the hand limit ended the match) has its own templates in MORE.
KINDS = tuple(k for k in FIELDS if k != "pk_limit")

# fmt: off
TEXT: dict[str, dict[str, tuple[str, ...]]] = {
    "en": {
        "epic": (
            "Round {round} began beneath the {card} banner, and the table of {players} fell silent.",
            "{player} laid {count} card(s) face down upon the wood and spoke a claim.",
            "Then {caller} rose and named {target} a liar!",
            "Bound by the law of the table, {caller} was forced to call {target} a liar.",
            "The cards turned: {cards}. No {card} among them. {target} had lied, and {caller} was proven right.",
            "The cards turned: {cards}. All true to the {card}. {caller} had accused an honest hand.",
            "{player} pulled the trigger, pull {pull}. Click. The chamber was empty.",
            "{player} pulled the trigger. A thunderclap, and {player} left the table forever.",
            "Alone at the end of the night stood {winner}, the last one breathing.",
            "Hand {hand} was dealt, the button resting with {button}, the big blind at {big_blind}.",
            "The {street} fell: {cards}.",
            "{player} raised the stakes to {to}.",
            "{player} pushed every last chip into the middle!",
            "{player} bowed out and let the hand go.",
            "The cards were shown: {hands}.",
            "{winners} claimed the pot of {amount}.",
            "{player}, stripped of every chip, was driven from the table.",
            "When the dust settled, {winner} sat alone with all the chips.",
            "The cast of this tale: {cast}.",
            "Night {night} fell over the village.",
            "Dawn came, and no one had fallen in the dark.",
            "{player}, the {role}, was found {cause}.",
            "Far off, a bear growled low: a wolf slept close to its master.",
            "The village voted, and {executed} fell with {votes} voice(s) against.",
            "The village could not agree, and no one was led to the gallows.",
            "With a last breath, {player} the Hunter loosed a shot and took {target} along.",
            "And so the tale ended: {outcome}",
        ),
        "news": (
            "ROUND {round}: the table card is {card}. Players: {players}.",
            "{player} puts down {count} card(s), face down.",
            "{caller} calls {target} a liar.",
            "{caller} is forced to call {target} a liar.",
            "The reveal: {cards}. Not a {card} in sight. {target} was lying; {caller} was right.",
            "The reveal: {cards}. All {card}. {caller} accused an honest player.",
            "{player} pulls the trigger (pull {pull}): empty chamber.",
            "BREAKING: {player} pulls the trigger. Live round. {player} is out.",
            "Final result: {winner} wins the match.",
            "HAND {hand}: button {button}, big blind {big_blind}.",
            "The {street}: {cards}.",
            "{player} raises to {to}.",
            "{player} goes all-in.",
            "{player} folds.",
            "Showdown: {hands}.",
            "{winners} takes the pot of {amount}.",
            "{player} is eliminated.",
            "Final result: {winner} wins all the chips.",
            "Tonight's cast: {cast}.",
            "NIGHT {night}: the village sleeps.",
            "Morning report: no deaths overnight.",
            "{player} ({role}) is dead: {cause}.",
            "Reports of a bear growling near the village.",
            "Vote result: {executed} is executed with {votes} vote(s).",
            "Vote result: no majority, no execution.",
            "Last-minute shot: {player}, the Hunter, takes {target} down.",
            "Final result: {outcome}",
        ),
        "sports": (
            "And we are off in round {round}! Table card: {card}. {players} at the table!",
            "{player} slides in {count} card(s), face down. Bold!",
            "Oh! {caller} calls it: LIAR, says {target}'s play!",
            "Forced hand for {caller}, who has to call {target} a liar!",
            "And the cards say {cards}. No {card}! {target} is caught, {caller} scores!",
            "And the cards say {cards}. All {card}! Terrible call by {caller}!",
            "{player} pulls, number {pull}... click! Safe, the crowd breathes again!",
            "{player} pulls... BANG! That is the end for {player}!",
            "That is the match! {winner} takes the title!",
            "Hand {hand} is on! {button} has the button, big blind is {big_blind}!",
            "The {street} is out: {cards}!",
            "{player} raises to {to}! Pressure!",
            "ALL IN from {player}! What a move!",
            "{player} lets it go. Folds.",
            "Showdown time: {hands}!",
            "{winners} takes down the pot of {amount}!",
            "{player} is out of chips, and out of the match!",
            "And {winner} wins it all, every chip!",
            "Tonight's line-up: {cast}.",
            "Night {night}, and the village goes quiet.",
            "Dawn breaks and everyone is still on their feet!",
            "{player}, the {role}, is down: {cause}!",
            "Listen! That is the bear growling!",
            "The vote is in: {executed} goes with {votes} vote(s)!",
            "A split vote, nobody goes this round!",
            "What a last play: {player}, the Hunter, fires and takes {target} with them!",
            "Final whistle: {outcome}",
        ),
        "novel": (
            "Round {round}. The table card was {card}, and {players} were already sweating.",
            "{player} slipped {count} card(s) onto the table. Please, please let nobody notice.",
            "\"Liar,\" said {caller}, looking straight at {target}.",
            "{caller} had no choice. \"Liar,\" came the flat word, aimed at {target}.",
            "The cards flipped over: {cards}. Not a single {card}. {target} winced; {caller} let out a breath.",
            "The cards flipped over: {cards}. All {card}. {caller} wanted the floor to swallow them.",
            "{player} squeezed the trigger (pull {pull}). Click. Just click. Their hands were shaking.",
            "{player} squeezed the trigger. The sound was louder than anything. And then {player} was gone.",
            "In the end only {winner} was left, somehow still sitting upright.",
            "Hand {hand}. {button} had the button, and the big blind was {big_blind}. Nobody spoke.",
            "The {street}: {cards}. Everyone studied them like a map.",
            "{player} nudged the stack forward to {to}. A tiny smile.",
            "\"All in,\" whispered {player}, and meant it.",
            "{player} sighed and folded.",
            "Cards up: {hands}.",
            "{winners} scooped up the {amount} chips, trying not to grin.",
            "{player} had no chips left, and quietly stood up.",
            "{winner} stared at the mountain of chips. It was over.",
            "Our cast: {cast}.",
            "Night {night}. The village held its breath.",
            "Morning came, and for once everybody was still there.",
            "They found {player}, the {role}, {cause}.",
            "Somewhere a bear growled. A shiver ran through the crowd.",
            "The hands went up: {executed} was chosen with {votes} vote(s). Nobody met their eyes.",
            "Nobody could decide. The day passed with no one on the gallows.",
            "{player}, the Hunter, raised a shaking bow and took {target} along.",
            "And that was how it ended: {outcome}",
        ),
    },
    "de": {
        "epic": (
            "Runde {round} begann unter dem Banner der Karte {card}, und der Tisch von {players} verstummte.",
            "{player} legte {count} Karte(n) verdeckt aufs Holz und sprach seine Behauptung.",
            "Da erhob sich {caller} und nannte {target} einen Lügner!",
            "Vom Gesetz des Tisches gezwungen, rief {caller}: {target} lügt!",
            "Die Karten wurden gewendet: {cards}. Keine Karte vom Typ {card} darunter. {target} hatte gelogen, und {caller} behielt recht.",
            "Die Karten wurden gewendet: {cards}. Alles wahr, alles {card}. {caller} hatte eine ehrliche Hand beschuldigt.",
            "{player} drückte ab, Zug {pull}. Klick. Die Kammer war leer.",
            "{player} drückte ab. Ein Donnerschlag, und {player} verließ den Tisch für immer.",
            "Allein am Ende der Nacht stand {winner}, der Letzte, der noch atmete.",
            "Hand {hand} wurde gegeben, der Knopf ruhte bei {button}, der große Blind bei {big_blind}.",
            "Der {street} fiel: {cards}.",
            "{player} erhöhte den Einsatz auf {to}.",
            "{player} schob alle Chips in die Mitte!",
            "{player} verneigte sich und ließ die Hand fahren.",
            "Die Karten wurden gezeigt: {hands}.",
            "{winners} gewann den Topf von {amount}.",
            "{player}, aller Chips beraubt, wurde vom Tisch gejagt.",
            "Als sich der Staub legte, saß {winner} allein mit allen Chips da.",
            "Die Besetzung dieser Geschichte: {cast}.",
            "Die Nacht {night} legte sich über das Dorf.",
            "Der Morgen kam, und niemand war in der Dunkelheit gefallen.",
            "{player} ({role}) wurde gefunden: {cause}.",
            "Fern brummte ein Bär: Ein Wolf schlief nah bei seinem Herrn.",
            "Das Dorf stimmte ab, und {executed} fiel mit {votes} Stimme(n) gegen sich.",
            "Das Dorf wurde sich nicht einig, und niemand wurde zum Galgen geführt.",
            "Mit dem letzten Atemzug schoss {player}, der Jäger, und nahm {target} mit.",
            "So endete die Geschichte: {outcome}",
        ),
        "news": (
            "RUNDE {round}: Tischkarte ist {card}. Spieler: {players}.",
            "{player} legt {count} Karte(n) verdeckt ab.",
            "{caller} ruft {target} einen Lügner.",
            "{caller} muss {target} einen Lügner nennen.",
            "Die Aufdeckung: {cards}. Keine Karte vom Typ {card} dabei. {target} hat gelogen, {caller} hatte recht.",
            "Die Aufdeckung: {cards}. Alles {card}. {caller} hat einen ehrlichen Spieler beschuldigt.",
            "{player} drückt ab (Zug {pull}): leere Kammer.",
            "EILMELDUNG: {player} drückt ab. Scharfer Schuss. {player} scheidet aus.",
            "Endergebnis: Sieger ist {winner}.",
            "HAND {hand}: Button {button}, großer Blind {big_blind}.",
            "Der {street}: {cards}.",
            "{player} erhöht auf {to}.",
            "{player} geht All-in.",
            "{player} passt.",
            "Showdown: {hands}.",
            "{winners} gewinnt den Topf von {amount}.",
            "{player} scheidet aus.",
            "Endergebnis: {winner} gewinnt alle Chips.",
            "Die heutige Besetzung: {cast}.",
            "NACHT {night}: Das Dorf schläft.",
            "Morgenbericht: Keine Toten in der Nacht.",
            "{player} ({role}) ist tot: {cause}.",
            "Berichte über einen brummenden Bären nahe dem Dorf.",
            "Abstimmungsergebnis: {executed} wird mit {votes} Stimme(n) hingerichtet.",
            "Abstimmungsergebnis: keine Mehrheit, keine Hinrichtung.",
            "Letzter Schuss: {player}, der Jäger, reißt {target} mit.",
            "Endergebnis: {outcome}",
        ),
        "sports": (
            "Und los geht es in Runde {round}! Tischkarte: {card}. {players} am Tisch!",
            "{player} schiebt {count} Karte(n) verdeckt rein. Mutig!",
            "Oh! {caller} ruft LÜGNER, direkt an {target}!",
            "Zwangslage für {caller}: {target} muss als Lügner angerufen werden!",
            "Und die Karten zeigen {cards}. Keine Karte vom Typ {card}! {target} ist erwischt, {caller} punktet!",
            "Und die Karten zeigen {cards}. Alles {card}! Ganz schwacher Ruf von {caller}!",
            "{player} drückt, Nummer {pull}... klick! Sicher, das Publikum atmet auf!",
            "{player} drückt... PENG! Das war es für {player}!",
            "Das ist das Spiel! {winner} holt den Titel!",
            "Hand {hand} läuft! {button} hat den Button, der große Blind ist {big_blind}!",
            "Der {street} ist da: {cards}!",
            "{player} erhöht auf {to}! Druck!",
            "ALL-IN von {player}! Was für ein Zug!",
            "{player} lässt es sein. Passt.",
            "Showdown: {hands}!",
            "{winners} räumt den Topf von {amount} ab!",
            "{player} ist ohne Chips, und raus aus dem Spiel!",
            "Und {winner} gewinnt alles, jeden einzelnen Chip!",
            "Die Aufstellung heute: {cast}.",
            "Nacht {night}, und das Dorf wird still.",
            "Der Morgen graut, und alle stehen noch auf den Beinen!",
            "{player} ({role}) ist gefallen: {cause}!",
            "Hören Sie! Das ist der Bär, der brummt!",
            "Die Abstimmung ist durch: {executed} muss mit {votes} Stimme(n) gehen!",
            "Gleichstand, diese Runde muss niemand gehen!",
            "Was für ein letzter Spielzug: {player}, der Jäger, schießt und nimmt {target} mit!",
            "Abpfiff: {outcome}",
        ),
        "novel": (
            "Runde {round}. Die Tischkarte war {card}, und {players} schwitzten bereits.",
            "{player} schob {count} Karte(n) auf den Tisch. Bitte, bitte, niemand soll es merken.",
            "„Lügner“, sagte {caller} und sah {target} direkt an.",
            "{caller} blieb keine Wahl. „Lügner“, kam es tonlos, gerichtet an {target}.",
            "Die Karten wurden umgedreht: {cards}. Keine einzige Karte vom Typ {card}. {target} zuckte zusammen, {caller} atmete aus.",
            "Die Karten wurden umgedreht: {cards}. Alles {card}. {caller} wäre am liebsten im Boden versunken.",
            "{player} drückte ab (Zug {pull}). Klick. Nur ein Klick. Die Hände zitterten.",
            "{player} drückte ab. Der Knall war lauter als alles andere. Und dann war {player} fort.",
            "Am Ende war nur noch {winner} übrig, irgendwie noch aufrecht sitzend.",
            "Hand {hand}. {button} hatte den Button, der große Blind war {big_blind}. Niemand sprach.",
            "Der {street}: {cards}. Alle studierten ihn wie eine Landkarte.",
            "{player} schob den Stapel auf {to}. Ein winziges Lächeln.",
            "„All-in“, flüsterte {player} und meinte es ernst.",
            "{player} seufzte und passte.",
            "Karten auf den Tisch: {hands}.",
            "{winners} strich die {amount} Chips ein und versuchte, nicht zu grinsen.",
            "{player} hatte keine Chips mehr und stand leise auf.",
            "{winner} starrte auf den Berg aus Chips. Es war vorbei.",
            "Unsere Besetzung: {cast}.",
            "Nacht {night}. Das Dorf hielt den Atem an.",
            "Der Morgen kam, und ausnahmsweise waren alle noch da.",
            "Man fand {player} ({role}): {cause}.",
            "Irgendwo brummte ein Bär. Ein Schauder ging durch die Menge.",
            "Die Hände gingen hoch: {executed} wurde mit {votes} Stimme(n) gewählt. Niemand sah dem anderen in die Augen.",
            "Keiner konnte sich entscheiden. Der Tag verging, ohne dass jemand an den Galgen kam.",
            "{player}, der Jäger, hob den zitternden Bogen und nahm {target} mit.",
            "Und so endete es: {outcome}",
        ),
    },
}

MORE: dict[str, dict[str, dict[str, str]]] = {
    "en": {
        "epic": {"pk_limit": "The hand limit fell, and the chips were counted: {leaders} stood highest."},
        "news": {"pk_limit": "Hand limit reached. Chip leader: {leaders}."},
        "sports": {"pk_limit": "That is the hand limit! {leaders} lead(s) the chip count!"},
        "novel": {"pk_limit": "The last hand was over. When they counted, {leaders} had the most chips."},
    },
    "de": {
        "epic": {"pk_limit": "Das Handlimit fiel, die Chips wurden gezählt: Am höchsten stand {leaders}."},
        "news": {"pk_limit": "Handlimit erreicht. Chipführer: {leaders}."},
        "sports": {"pk_limit": "Das ist das Handlimit! Chipführer ist {leaders}!"},
        "novel": {"pk_limit": "Die letzte Hand war vorbei. Beim Zählen hatte {leaders} die meisten Chips."},
    },
}

OUTCOMES = {
    "en": {
        "wolves": "the wolves have won.", "village": "the village has won.",
        "lovers": "the lovers have won.", "white_wolf": "the White Werewolf has won.",
        "nobody": "nobody has won.",
    },
    "de": {
        "wolves": "die Wölfe haben gewonnen.", "village": "das Dorf hat gewonnen.",
        "lovers": "das Liebespaar hat gewonnen.", "white_wolf": "der Weiße Werwolf hat gewonnen.",
        "nobody": "niemand hat gewonnen.",
    },
}

CHAPTER_TITLES: dict[str, dict[str, dict[str, str]]] = {
    "en": {
        "epic": {"round": "The Round of the {nth} Trial", "hand": "The {nth} Hand of Fate", "night": "The {nth} Night"},
        "news": {"round": "Round {n}", "hand": "Hand {n}", "night": "Night {n} and the Day After"},
        "sports": {"round": "Round {n}", "hand": "Hand {n}", "night": "Night {n}, Day {n}"},
        "novel": {"round": "Round {n}: Sweaty Palms", "hand": "Hand {n}: Poker Faces", "night": "Chapter {n}: The Long Night"},
    },
    "de": {
        "epic": {"round": "Die Runde der {n}. Prüfung", "hand": "Die {n}. Hand des Schicksals", "night": "Die {n}. Nacht"},
        "news": {"round": "Runde {n}", "hand": "Hand {n}", "night": "Nacht {n} und der Tag danach"},
        "sports": {"round": "Runde {n}", "hand": "Hand {n}", "night": "Nacht {n}, Tag {n}"},
        "novel": {"round": "Runde {n}: Schwitzige Hände", "hand": "Hand {n}: Pokergesichter", "night": "Kapitel {n}: Die lange Nacht"},
    },
}

TITLES: dict[str, dict[str, str]] = {
    "en": {
        "epic": "The Saga of {game}",
        "news": "{game}: The Full Report",
        "sports": "{game}: Match Commentary",
        "novel": "{game}: A Story",
    },
    "de": {
        "epic": "Die Saga von {game}",
        "news": "{game}: Der vollständige Bericht",
        "sports": "{game}: Die Spielkommentare",
        "novel": "{game}: Eine Geschichte",
    },
}

GAME_NAMES = {"liars_deck": "Liar's Deck", "poker": "Poker", "werewolf": "Werewolf"}

CARDS = {
    "en": {"K": "King", "Q": "Queen", "A": "Ace", "J": "Joker", "DV": "Devil card"},
    "de": {"K": "König", "Q": "Dame", "A": "Ass", "J": "Joker", "DV": "Teufelskarte"},
}
RANKS = {
    "en": {"king": "King", "queen": "Queen", "ace": "Ace"},
    "de": {"king": "König", "queen": "Dame", "ace": "Ass"},
}
STREETS = {
    "en": {"flop": "flop", "turn": "turn", "river": "river"},
    "de": {"flop": "Flop", "turn": "Turn", "river": "River"},
}
POKER_HANDS = {
    "en": {
        "high_card": "high card", "one_pair": "one pair", "two_pair": "two pair",
        "three_of_a_kind": "three of a kind", "straight": "a straight", "flush": "a flush",
        "full_house": "a full house", "four_of_a_kind": "four of a kind",
        "straight_flush": "a straight flush", "royal_flush": "a royal flush",
    },
    "de": {
        "high_card": "Höchste Karte", "one_pair": "ein Paar", "two_pair": "zwei Paare",
        "three_of_a_kind": "ein Drilling", "straight": "eine Straße", "flush": "ein Flush",
        "full_house": "ein Full House", "four_of_a_kind": "ein Vierling",
        "straight_flush": "ein Straight Flush", "royal_flush": "ein Royal Flush",
    },
}
CAUSES = {
    "en": {
        "wolves": "torn apart by the wolves", "executed": "executed by the village",
        "poison": "poisoned", "hunter": "shot by the Hunter", "grief": "dead of grief",
        "caught_spying": "caught spying", "white_wolf": "killed by the White Werewolf",
        "scapegoat": "taken as the scapegoat",
    },
    "de": {
        "wolves": "von den Wölfen gerissen", "executed": "vom Dorf hingerichtet",
        "poison": "vergiftet", "hunter": "vom Jäger erschossen", "grief": "vor Kummer gestorben",
        "caught_spying": "beim Spionieren erwischt", "white_wolf": "vom Weißen Werwolf getötet",
        "scapegoat": "als Sündenbock geopfert",
    },
}
WINNERS = {
    "en": {"wolves": "the wolves", "village": "the village", "lovers": "the lovers",
           "white_wolf": "the White Werewolf", "nobody": "nobody"},
    "de": {"wolves": "die Wölfe", "village": "das Dorf", "lovers": "das Liebespaar",
           "white_wolf": "der Weiße Werwolf", "nobody": "niemand"},
}
# fmt: on


class Narrator:
    """Turns the beats of one chapter into text. Subclass it to retell a chapter another way.

    A model-based narrator can take the chapter's beats (plain facts) and the
    template text as a draft; `TemplateNarrator` is the default and costs nothing.
    """

    def title(self, game: str, style: str, lang: str) -> str:
        raise NotImplementedError

    def chapter_title(self, kind: str, number: int, style: str, lang: str) -> str:
        raise NotImplementedError

    def tell(self, beats: list[Beat], style: str, lang: str, names: Mapping[str, str]) -> str:
        raise NotImplementedError


class TemplateNarrator(Narrator):
    """Fixed templates: the same beats always give the same words."""

    def title(self, game: str, style: str, lang: str) -> str:
        return TITLES[lang][style].format(game=GAME_NAMES.get(game, game))

    def chapter_title(self, kind: str, number: int, style: str, lang: str) -> str:
        return CHAPTER_TITLES[lang][style][kind].format(n=number, nth=_ordinal(number))

    def tell(self, beats: list[Beat], style: str, lang: str, names: Mapping[str, str]) -> str:
        templates = dict(zip(KINDS, TEXT[lang][style], strict=True)) | MORE[lang][style]
        return " ".join(templates[beat.kind].format(**_fields(beat, lang, names)) for beat in beats)


def _ordinal(n: int) -> str:
    if 10 <= n % 100 <= 20:
        return f"{n}th"
    return f"{n}" + {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")


def _who(player: Any, names: Mapping[str, str]) -> str:
    return names.get(player, str(player))


def _list(players: list[Any], names: Mapping[str, str], lang: str) -> str:
    named = [_who(p, names) for p in players]
    if len(named) <= 1:
        return "".join(named)
    return ", ".join(named[:-1]) + (" and " if lang == "en" else " und ") + named[-1]


def _card(card: str, lang: str) -> str:
    key = "DV" if card == "DV" else card[0]
    word = CARDS[lang][key]
    return word if key in ("DV", "J") else f"{word} {card[1:]}"


def _role(role: str, lang: str) -> str:
    if lang == "de":
        from games.werewolf.selection import (
            load_roles,
        )  # German display names live in the role files

        return load_roles()[role].name
    return role.replace("_", " ")


def _fields(beat: Beat, lang: str, names: Mapping[str, str]) -> dict[str, str]:
    """The template fields of a beat as words, with names and the language applied."""
    f = beat.facts
    out: dict[str, str] = {}
    for key in FIELDS[beat.kind]:
        value = f[key]
        if key in ("player", "caller", "target", "button", "winner", "executed"):
            out[key] = _who(value, names) if value is not None else WINNERS[lang]["nobody"]
        elif key == "outcome":
            text = OUTCOMES[lang].get(value, OUTCOMES[lang]["nobody"])
            out[key] = text[0].upper() + text[1:]
        elif key in ("players", "winners", "leaders"):
            out[key] = _list(value, names, lang)
        elif key == "card":
            out[key] = RANKS[lang][value]
        elif key == "cards" and beat.kind in ("ld_caught", "ld_wrong"):
            out[key] = ", ".join(_card(c, lang) for c in value)
        elif key == "cards":
            out[key] = " ".join(value)
        elif key == "street":
            out[key] = STREETS[lang][value]
        elif key == "hands":
            out[key] = "; ".join(
                f"{_who(h['player'], names)} ({POKER_HANDS[lang][h['hand']]}: {' '.join(h['cards'])})"
                for h in value
            )
        elif key == "cast":
            out[key] = ", ".join(f"{_who(p, names)} ({_role(r, lang)})" for p, r in value.items())
        elif key == "role":
            out[key] = _role(value, lang)
        elif key == "cause":
            out[key] = CAUSES[lang].get(value, value.replace("_", " "))
        else:
            out[key] = str(value)
    return out
