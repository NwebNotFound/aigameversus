"""The Poker chronicle: a chapter per blind level, the big pots, the bluffs and the busts.

No seat id in the text, no sentence told twice, a different shape per style, the same log the
same story, the facts of a hand told right, and golden files for the real example match.
"""

import asyncio
import json
import os
import re
import string
from pathlib import Path

import pytest

from arena.agents.random_bot import random_bots
from arena.chronicle import LANGS, STYLES, tell, to_markdown
from arena.chronicle.compose import FIELDS_BY_GAME, templates
from arena.engine.match import Match
from arena.engine.types import MESSAGE, Event, EventSource
from arena.transcript.common import display_names
from games.poker.plugin import Poker

ROOT = Path(__file__).resolve().parents[2]
GOLDEN = Path(__file__).parent / "golden"
SEAT = re.compile(r"\bp\d+\b", re.IGNORECASE)
EXAMPLE = json.loads((ROOT / "docs" / "examples" / "poker.json").read_text(encoding="utf-8"))
EVENTS = [Event(**e) for e in EXAMPLE["events"]]
NAMES = display_names({seat: ("model", model) for seat, model in EXAMPLE["seats"].items()})
FIELDS = FIELDS_BY_GAME["poker"]


def story(style="epic", lang="en", events=EVENTS, names=NAMES, **kwargs):
    return tell(events, style=style, lang=lang, names=names, **kwargs)


def all_text(chronicle) -> str:
    glance = [f"{g.label}: {g.value}" for g in chronicle.glance]
    parts = [chronicle.title, chronicle.glance_title, *glance]
    return "\n".join(parts + [f"{c.title}\n{c.text}" for c in chronicle.chapters])


def sentences(chronicle) -> list[str]:
    text = "\n".join(c.text for c in chronicle.chapters)
    return [s.strip("- ").strip() for s in re.split(r"(?<=[.!?…])\s+|\n+", text) if s.strip("- ")]


def game(type_, data, visible_to=None):
    return Event(source=EventSource.GAME, type=type_, data=data, visible_to=visible_to)


def hand(n, *events, big=20):
    start = {"hand": n, "button": "p1", "players": ["p1", "p2"], "big_blind": big}
    return [game("hand_started", start | {"small_blind": big // 2}), *events]


def pot(amount, winner, eligible=("p1", "p2")):
    return game(
        "pot_awarded", {"amount": amount, "shares": {winner: amount}, "eligible": list(eligible)}
    )


def bet(player, kind, to=0):
    return game(
        "bet_action", {"player": player, "kind": kind, "to": to, "added": to, "street": "flop"}
    )


def heads_up(*hands, winner="p2", reason="last_player"):
    placements = [
        {"player": winner, "rank": 1},
        {"player": "p1" if winner == "p2" else "p2", "rank": 2},
    ]
    start = {"game": "poker", "version": "1", "players": ["p1", "p2"], "seed": 1}
    return [
        Event(
            source=EventSource.ENGINE,
            type="match_started",
            data=start | {"settings": {"double_every": 2}},
            visible_to=(),
        ),
        *[e for h in hands for e in h],
        game(
            "match_over", {"reason": reason, "winner": winner if reason == "last_player" else None}
        ),
        Event(source=EventSource.ENGINE, type="match_finished", data={"placements": placements}),
    ]


def bot_events(seed, players):
    plugin = Poker()
    seats = [f"p{i}" for i in range(1, players + 1)]
    match = Match(plugin, random_bots(plugin, seats, seed), seed=seed)
    asyncio.run(match.run())
    return match.events


@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize("style", STYLES)
def test_no_seat_id_reaches_the_text_and_no_sentence_is_told_twice(style, lang):
    chronicle = story(style, lang)
    text = all_text(chronicle)
    told = sentences(chronicle)

    assert not SEAT.search(text), SEAT.findall(text)
    assert "{" not in text and "}" not in text
    assert all(name in text for name in NAMES.values())
    assert not {s for s in told if told.count(s) > 1}


@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize("style", STYLES)
def test_the_chapters_are_a_prologue_one_per_blind_level_and_an_epilogue(style, lang):
    chronicle = story(style, lang)

    levels = {(e.data["hand"] - 1) // 5 for e in EVENTS if e.type == "hand_started"}
    assert [c.kind for c in chronicle.chapters] == [
        "prologue",
        *["level"] * len(levels),
        "epilogue",
    ]
    assert [c.seq for c in chronicle.chapters] == sorted(c.seq for c in chronicle.chapters)


@pytest.mark.parametrize("lang", LANGS)
def test_the_styles_differ_in_structure_and_in_words(lang):
    told = {style: story(style, lang) for style in STYLES}

    assert len({c.title for c in told.values()}) == len(STYLES)
    assert len({tuple(ch.title for ch in c.chapters) for c in told.values()}) == len(STYLES)
    assert len({c.chapters[1].text for c in told.values()}) == len(STYLES)
    assert all(line.startswith("- ") for c in told["news"].chapters for line in c.text.split("\n"))
    assert any("\n" in c.text for c in told["sports"].chapters)
    assert any("\n\n" in c.text for c in told["novel"].chapters)
    assert all("\n" not in c.text for c in told["epic"].chapters)


def test_the_real_match_tells_its_big_pots_its_busts_and_the_chip_leader():
    chronicle = story("news", "en")
    text = "\n".join(c.text for c in chronicle.chapters)
    glance = {g.label: g.value for g in chronicle.glance}

    assert "Opening blinds: 10/20." in text or "Blinds start at 10/20." in text  # not "rose"
    assert "2970" in text and "two pair" in text and "a flush" in text
    assert re.search(r"claude-haiku (is eliminated|busts)|Out in hand 2: claude-haiku", text)
    assert "gemini-flash-lite leads on chips" in text  # the hand limit, not a winner
    assert glance["Winner"] == "gemini-flash-lite (chip leader at the hand limit)"
    assert glance["Biggest pot"] == "Hand 2: gemini-flash-lite wins 2970 chips"
    assert glance["Best hand shown"] == "gemini-flash-lite (a flush)"
    assert glance["Length"] == "20 hands"


def test_a_bluff_a_showdown_a_split_and_a_small_pot_are_told_apart():
    log = heads_up(
        hand(  # a raise with nothing on the board, everybody folds: a bluff
            1,
            game("hole_dealt", {"player": "p2", "cards": ["2c", "7d"]}),
            game("street_started", {"street": "flop", "cards": ["Ks", "9h", "4d"]}),
            bet("p2", "raise", 200),
            bet("p1", "fold"),
            pot(400, "p2"),
            game("hand_ended", {"hand": 1, "showdown": False}),
        ),
        hand(  # a showdown: a straight against two pair
            2,
            game("showdown", {"hands": [
                {"player": "p1", "hand": "two_pair", "cards": ["Ks", "9h"]},
                {"player": "p2", "hand": "straight", "cards": ["Tc", "Jd"]},
            ]}),
            pot(600, "p2"),
            game("hand_ended", {"hand": 2, "showdown": True}),
        ),
        hand(  # equal hands: a split
            3,
            game("pot_awarded", {"amount": 300, "shares": {"p1": 150, "p2": 150},
                                 "eligible": ["p1", "p2"]}),
            game("hand_ended", {"hand": 3, "showdown": True}),
        ),
        hand(4, pot(60, "p1"), game("hand_ended", {"hand": 4, "showdown": False})),  # too small
    )  # fmt: skip

    text = "\n".join(c.text for c in story("news", "en", events=log, names={}).chapters)

    assert re.search(r"Hand 1: p2 wins 400 chips with no pair|Bluff in hand 1|p2 bluffs", text)
    assert "a straight" in text and "two pair" in text and "600" in text
    assert "split" in text and "300" in text
    assert "Hand 4" not in text and "60 chips" not in text


def test_a_pot_returned_uncalled_is_not_counted_as_won():
    log = heads_up(
        hand(
            1,
            pot(500, "p2"),
            pot(120, "p2", eligible=("p2",)),  # the bet nobody called, back to its owner
            game("hand_ended", {"hand": 1, "showdown": True}),
        )
    )

    text = "\n".join(c.text for c in story("news", "en", events=log, names={}).chapters)

    assert "500" in text and "620" not in text


def test_one_quote_per_level_and_the_hand_limit_names_the_leader_in_german():
    log = heads_up(
        hand(
            1, game(MESSAGE, {"player": "p1", "text": "p2, you will not see the river this time."})
        ),
        hand(
            2, game(MESSAGE, {"player": "p2", "text": "We shall see who folds first here today."})
        ),
        reason="hand_limit",
    )

    names = {"p1": "Ann", "p2": "Ben"}
    text = "\n".join(c.text for c in story("epic", "de", events=log, names=names).chapters)

    assert "Ben, you will not see the river this time." in text  # a seat id becomes a name
    assert "We shall see" not in text  # the same level: one quote
    assert "am höchsten stand Ben" in text


def test_german_names_the_hands_after_mit():
    text = all_text(story("news", "de"))

    assert "mit zwei Paaren" in text and "mit einem Flush" in text
    assert "two pair" not in text


def test_the_key_moments_point_at_pots_and_busts():
    moments = story().key_moments

    assert {"pot", "busted"} <= {m["kind"] for m in moments}
    for moment in moments:
        assert EVENTS[moment["seq"]].type in {"hand_started", "players_eliminated"}
        assert moment["players"] and len(moment["players"]) == len(set(moment["players"]))


def test_the_same_log_tells_the_same_story_and_another_seed_another_one():
    first = to_markdown(story("novel", "en"))
    start = EVENTS[0].model_copy(update={"data": {**EVENTS[0].data, "seed": 99}})

    assert first == to_markdown(story("novel", "en"))
    assert first != to_markdown(story("novel", "en", events=[start, *EVENTS[1:]]))


@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize("style", STYLES)
def test_every_template_variant_only_uses_fields_of_its_kind(style, lang):
    tpl = templates("poker", lang)[style]
    kinds = tpl["kinds"]

    assert set(kinds) == set(FIELDS), set(kinds) ^ set(FIELDS)
    for kind, variants in kinds.items():
        assert variants, (style, lang, kind)
        for variant in variants:
            used = {name for _, name, _, _ in string.Formatter().parse(variant) if name}
            assert used <= set(FIELDS[kind]), (style, lang, kind, used - set(FIELDS[kind]))
    assert len(kinds["level_starts"]) >= 4 and tpl["again"]


@pytest.mark.parametrize(("seed", "players"), [(1, 2), (3, 3), (5, 6), (8, 4)])
def test_real_bot_matches_tell_without_a_seat_id_or_a_repeated_sentence(seed, players):
    events = bot_events(seed, players)
    names = display_names({p: ("bot", p) for p in events[0].data["players"]})

    for lang in LANGS:
        for style in STYLES:
            chronicle = tell(events, style=style, lang=lang, names=names)
            assert not SEAT.search(all_text(chronicle)), (seed, style, lang)
            told = sentences(chronicle)
            assert not {s for s in told if told.count(s) > 1}, (seed, style, lang)
            assert chronicle.chapters[0].kind == "prologue"
            assert chronicle.chapters[-1].kind == "epilogue"


@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize("style", STYLES)
def test_golden_chronicle_of_the_real_example_match(style, lang):
    text = to_markdown(story(style, lang, cost_micro_eur=23411))
    path = GOLDEN / f"poker_{style}_{lang}.md"
    if os.environ.get("UPDATE_GOLDEN"):
        path.parent.mkdir(exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")

    assert path.exists(), f"{path.name} is missing; run with UPDATE_GOLDEN=1"
    assert text == path.read_text(encoding="utf-8"), (
        f"{path.name} changed; UPDATE_GOLDEN=1 if intended"
    )


def test_a_win_with_nothing_is_a_bluff_only_after_a_bet_and_a_pair_is_no_best_hand():
    log = heads_up(
        hand(  # p2 holds nothing and never bet: p1 simply let go
            1,
            game("hole_dealt", {"player": "p2", "cards": ["2c", "7d"]}),
            game("street_started", {"street": "flop", "cards": ["Ks", "9h", "4d"]}),
            bet("p1", "fold"),
            pot(400, "p2"),
            game("hand_ended", {"hand": 1, "showdown": False}),
        ),
        hand(  # the only showdown shows a pair: not worth "best hand"
            2,
            game("showdown", {"hands": [
                {"player": "p1", "hand": "high_card", "cards": ["2s", "3h"]},
                {"player": "p2", "hand": "one_pair", "cards": ["Ks", "Kh"]},
            ]}),
            pot(600, "p2"),
            game("hand_ended", {"hand": 2, "showdown": True}),
        ),
    )  # fmt: skip

    chronicle = story("news", "en", events=log, names={})
    text = "\n".join(c.text for c in chronicle.chapters)

    assert "luff" not in text and "no pair" not in text
    assert re.search(r"Hand 1: p2 wins 400 chips without a showdown|uncontested|No showdown", text)
    assert "Best hand shown" not in {g.label for g in chronicle.glance}
