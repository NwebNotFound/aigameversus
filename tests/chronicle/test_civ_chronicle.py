"""The Throne of Tokens chronicle: ages of ten rounds, wars, treaties and conquests, four styles.

No seat id in the text, no sentence told twice, a different shape per style, the same log the
same story, diplomacy told from a log that has it, and golden files for one bot match.
"""

import asyncio
import os
import re
import string
from functools import cache
from pathlib import Path

import pytest

from arena.agents.random_bot import random_bots
from arena.chronicle import LANGS, STYLES, chronicle_games, tell, to_markdown
from arena.chronicle.ai import check_chapter
from arena.chronicle.compose import FIELDS_BY_GAME, templates
from arena.engine.match import Match
from arena.engine.types import MESSAGE, Event, EventSource
from games.civ.plugin import CivGame

GOLDEN = Path(__file__).parent / "golden"
SEAT = re.compile(r"\bp\d+\b", re.IGNORECASE)
FIELDS = FIELDS_BY_GAME["civ"]
NAMES = {"p1": "Ada", "p2": "Bo", "p3": "Cy", "p4": "Di", "p5": "Ed", "p6": "Flo"}


@cache
def bot_events(seed: int = 3, players: int = 4, rounds: int = 60) -> tuple[Event, ...]:
    plugin = CivGame()
    seats = [f"p{i}" for i in range(1, players + 1)]
    match = Match(plugin, random_bots(plugin, seats, seed), seed=seed, settings={"rounds": rounds})
    asyncio.run(match.run())
    return tuple(match.events)


def story(style="epic", lang="en", events=None, **kwargs):
    return tell(list(events or bot_events()), style=style, lang=lang, names=NAMES, **kwargs)


def all_text(chronicle) -> str:
    glance = [f"{g.label}: {g.value}" for g in chronicle.glance]
    parts = [chronicle.title, chronicle.glance_title, *glance]
    return "\n".join(parts + [f"{c.title}\n{c.text}" for c in chronicle.chapters])


def sentences(chronicle) -> list[str]:
    text = "\n".join(c.text for c in chronicle.chapters)
    return [s.strip("- ").strip() for s in re.split(r"(?<=[.!?…])\s+|\n+", text) if s.strip("- ")]


def game(type_: str, data: dict, visible_to=None) -> Event:
    return Event(source=EventSource.GAME, type=type_, data=data, visible_to=visible_to)


def diplomatic_log() -> list[Event]:
    """A short match with what random bots never do: talk, treaties, a war, a broken word."""
    standings = [
        {"player": "p1", "score": 90, "rank": 1},
        {"player": "p2", "score": 40, "rank": 2},
        {"player": "p3", "score": 30, "rank": 3},
        {"player": "p4", "score": 10, "rank": 4},
    ]
    placements = [{"player": s["player"], "rank": s["rank"]} for s in standings]
    start = {"game": "civ", "version": "2", "players": ["p1", "p2", "p3", "p4"], "seed": 4}
    founded = [
        game("city_founded", {"city": f"c{i}", "owner": f"p{i}", "col": i, "row": 0})
        for i in range(1, 5)
    ]
    return [
        Event(
            source=EventSource.ENGINE,
            type="match_started",
            data=start | {"settings": {"rounds": 12}},
            visible_to=(),
        ),
        *founded,
        game("round_started", {"round": 1}),
        game(MESSAGE, {"player": "p1", "text": "p2, join me and we will rule the north together."}),
        game(MESSAGE, {"player": "p3", "text": "Nobody in the south wants a war with p4 now."}),
        game(
            "treaty_signed",
            {"treaty": "t1", "kind": "alliance", "parties": ["p1", "p2"], "ends_war": False},
        ),
        game("economy_countdown", {"rounds": {"p3": 1}, "needed": 5}),
        game("round_started", {"round": 2}),
        game("economy_countdown", {"rounds": {"p3": 2}, "needed": 5}),
        game("war_declared", {"by": "p1", "on": "p4", "broken": [], "joined": []}),
        game(
            "battle",
            {
                "tile": [4, 0],
                "attacker": {"nation": "p1", "army": "a1", "lost": ["spearman"]},
                "defender": {"nation": "p4", "city": "c4", "lost": ["archer", "spearman", "scout"]},
                "winner": "p1",
            },
            visible_to=("p1", "p4"),
        ),
        game("city_conquered", {"city": "c4", "from": "p4", "to": "p1", "round": 2}),
        game("round_started", {"round": 11}),
        game("treaty_broken", {"treaty": "t1", "by": "p2"}),
        game(
            "treaty_signed",
            {"treaty": "t2", "kind": "peace", "parties": ["p1", "p4"], "ends_war": True},
        ),
        game(
            "victory",
            {
                "kind": "domination",
                "winners": ["p1"],
                "round": 11,
                "standings": standings,
                "placements": placements,
            },
        ),
        Event(source=EventSource.ENGINE, type="match_finished", data={"placements": placements}),
    ]


def test_civ_has_a_chronicle():
    assert "civ" in chronicle_games()


@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize("style", STYLES)
def test_no_seat_id_reaches_the_text_and_no_sentence_is_told_twice(style, lang):
    chronicle = story(style, lang)
    text = all_text(chronicle)
    told = sentences(chronicle)

    assert not SEAT.search(text), SEAT.findall(text)
    assert "{" not in text and "}" not in text
    assert all(NAMES[s] in text for s in ("p1", "p2", "p3", "p4"))
    assert not {s for s in told if told.count(s) > 1}


@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize("style", STYLES)
def test_the_chapters_are_a_prologue_one_per_age_of_ten_rounds_and_an_epilogue(style, lang):
    chronicle = story(style, lang)

    assert [c.kind for c in chronicle.chapters] == ["prologue", *["age"] * 6, "epilogue"]
    assert [c.number for c in chronicle.chapters] == list(range(1, 9))
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


def test_the_barbarians_are_one_name_with_a_capital_at_the_start_of_a_sentence():
    for lang, word in (("en", "barbarian horde"), ("de", "Barbarenhorde")):
        text = "\n".join(c.text for c in story("epic", lang).chapters)
        assert word in text
        assert not re.search(rf"(^|[.!?]\s)(the|die) {word}", text)  # "The ...", "Die ..."
    assert "1 units" not in all_text(story("epic", "en"))


def test_diplomacy_war_conquest_talk_and_the_gold_race_are_told():
    chronicle = story("news", "en", events=diplomatic_log())
    text = "\n".join(c.text for c in chronicle.chapters)

    assert "Ada and Bo sign" in text and "Alliance" in text
    assert re.search(r"Ada (declares war on|opens hostilities with) Di|War: Ada against Di", text)
    assert "Ada" in text and "4 units" not in text and "3 units" in text  # the defender's losses
    assert re.search(r"Ada captures the capital of Di|Capital falls: Di loses its capital", text)
    assert "Bo breaks" in text or "Treaty broken: Bo" in text
    assert re.search(r"Ada and Di (sign a peace|end hostilities)|Peace agreed: Ada and Di", text)
    assert "Bo, join me and we will rule the north together." in text  # the seat id named
    assert "Nobody in the south" not in text  # one quote per age
    assert len(re.findall(r"Cy starts the gold countdown|Economic race: Cy", text)) == 1
    assert "Ada wins by domination in round 11" in text
    assert "1. Ada (90), 2. Bo (40), 3. Cy (30), 4. Di (10)" in text
    glance = {g.label: g.value for g in chronicle.glance}
    assert glance["Winner"] == "Ada (domination)"
    assert glance["Most conquests"] == "Ada (1 city taken)"
    assert glance["Most treaties"] == "Ada (2 treaties)"
    assert "Age 1" in glance["Key moment"] and "Ada" in glance["Key moment"]


def test_german_names_the_treaties_in_german():
    text = "\n".join(c.text for c in story("epic", "de", events=diplomatic_log()).chapters)

    assert "Bündnis" in text and "Frieden" in text and "Einheiten" in text


def test_the_key_moments_point_at_their_events_and_name_only_nations():
    events = diplomatic_log()
    moments = story(events=events).key_moments

    assert {"treaty", "war", "battle", "conquest", "broken"} <= {m["kind"] for m in moments}
    types = {"treaty_signed", "war_declared", "battle", "city_conquered", "treaty_broken"}
    for moment in moments:
        assert events[moment["seq"]].type in types | {"random_event"}
        assert set(moment["players"]) <= {"p1", "p2", "p3", "p4"}
    barbarian = [m for m in story().key_moments if m["kind"] == "battle"]
    assert barbarian and all(set(m["players"]) <= {"p1", "p2", "p3", "p4"} for m in barbarian)


def test_the_same_log_tells_the_same_story_and_another_seed_another_one():
    events = list(bot_events())
    first = to_markdown(story("novel", "en", events=events))
    start = events[0].model_copy(update={"data": {**events[0].data, "seed": 99}})

    assert first == to_markdown(story("novel", "en", events=events))
    assert first != to_markdown(story("novel", "en", events=[start, *events[1:]]))


@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize("style", STYLES)
def test_every_template_variant_only_uses_fields_of_its_kind(style, lang):
    tpl = templates("civ", lang)[style]
    kinds = tpl["kinds"]

    assert set(kinds) == set(FIELDS), set(kinds) ^ set(FIELDS)
    for kind, variants in kinds.items():
        assert variants, (style, lang, kind)
        for variant in variants:
            used = {name for _, name, _, _ in string.Formatter().parse(variant) if name}
            assert used <= set(FIELDS[kind]), (style, lang, kind, used - set(FIELDS[kind]))
    assert len(kinds["age_starts"]) >= 4 and tpl["again"]
    assert set(tpl["glance_values"]["winner"]) == {"domination", "economy", "round_limit"}


@pytest.mark.parametrize(("seed", "players"), [(1, 4), (5, 5), (11, 6), (8, 4)])
def test_real_bot_matches_tell_without_a_seat_id_or_a_repeated_sentence(seed, players):
    events = list(bot_events(seed, players, 20 + seed))

    for lang in LANGS:
        for style in STYLES:
            chronicle = story(style, lang, events=events)
            assert not SEAT.search(all_text(chronicle)), (seed, style, lang)
            told = sentences(chronicle)
            assert not {s for s in told if told.count(s) > 1}, (seed, style, lang)
            assert chronicle.chapters[0].kind == "prologue"
            assert chronicle.chapters[-1].kind == "epilogue"


def test_a_retelling_that_invents_a_unit_or_a_resource_is_refused_by_the_fact_check():
    template = "Ada attacked Bo and won; Ada lost 1 unit, Bo 3 units."

    assert (
        check_chapter("Ada beat Bo; Ada lost 1 unit, Bo 3 units.", template, ["Ada", "Bo"]) is None
    )
    assert "swordsman" in check_chapter(
        "Ada's swordsman beat Bo; Ada lost 1 unit, Bo 3 units.", template, ["Ada", "Bo"]
    )
    assert "gold" in check_chapter(
        "Ada beat Bo for gold; Ada lost 1 unit, Bo 3 units.", template, ["Ada", "Bo"]
    )


@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize("style", STYLES)
def test_golden_chronicle_of_a_bot_match(style, lang):
    text = to_markdown(story(style, lang, cost_micro_eur=0))
    path = GOLDEN / f"civ_{style}_{lang}.md"
    if os.environ.get("UPDATE_GOLDEN"):
        path.parent.mkdir(exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")

    assert path.exists(), f"{path.name} is missing; run with UPDATE_GOLDEN=1"
    assert text == path.read_text(encoding="utf-8"), (
        f"{path.name} changed; UPDATE_GOLDEN=1 if intended"
    )
