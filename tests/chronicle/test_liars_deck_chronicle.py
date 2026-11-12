"""The Liar's Deck chronicle: a story of bluffs, calls and shots, in display names, four styles.

No seat id in the text, no sentence told twice (also in a ten-round heads-up duel), a different
shape per style, the same log the same story, and golden files for the real example match.
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
from arena.engine.types import Event
from arena.transcript.common import display_names
from games.liars_deck.plugin import LiarsDeck

ROOT = Path(__file__).resolve().parents[2]
GOLDEN = Path(__file__).parent / "golden"
SEAT = re.compile(r"\bp\d+\b", re.IGNORECASE)
EXAMPLE = json.loads((ROOT / "docs" / "examples" / "liars_deck.json").read_text(encoding="utf-8"))
EVENTS = [Event(**e) for e in EXAMPLE["events"]]
NAMES = display_names({seat: ("model", model) for seat, model in EXAMPLE["seats"].items()})
FIELDS = FIELDS_BY_GAME["liars_deck"]


def story(style="epic", lang="en", events=EVENTS, names=NAMES, **kwargs):
    return tell(events, style=style, lang=lang, names=names, **kwargs)


def all_text(chronicle) -> str:
    glance = [f"{g.label}: {g.value}" for g in chronicle.glance]
    parts = [chronicle.title, chronicle.glance_title, *glance]
    return "\n".join(parts + [f"{c.title}\n{c.text}" for c in chronicle.chapters])


def sentences(chronicle) -> list[str]:
    text = "\n".join(c.text for c in chronicle.chapters)
    return [s.strip("- ").strip() for s in re.split(r"(?<=[.!?…])\s+|\n+", text) if s.strip("- ")]


def bot_events(seed, players=3, settings=None):
    plugin = LiarsDeck()
    seats = [f"p{i}" for i in range(1, players + 1)]
    match = Match(plugin, random_bots(plugin, seats, seed), seed=seed, settings=settings or {})
    asyncio.run(match.run())
    return match.events


@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize("style", STYLES)
def test_no_seat_id_reaches_the_text_and_every_player_is_a_display_name(style, lang):
    text = all_text(story(style, lang))

    assert not SEAT.search(text), SEAT.findall(text)
    assert "{" not in text and "}" not in text
    for name in NAMES.values():
        assert name in text


@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize("style", STYLES)
def test_no_sentence_is_told_twice_even_in_a_ten_round_duel(style, lang):
    chronicle = story(style, lang)
    told = sentences(chronicle)

    assert sum(c.kind == "round" for c in chronicle.chapters) >= 10
    assert not {s for s in told if told.count(s) > 1}


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


@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize("style", STYLES)
def test_the_chapters_are_prologue_one_per_round_and_epilogue(style, lang):
    chronicle = story(style, lang)

    rounds = sum(e.type == "round_started" for e in EVENTS)
    kinds = [c.kind for c in chronicle.chapters]
    assert kinds == ["prologue", *["round"] * rounds, "epilogue"]
    assert [c.number for c in chronicle.chapters] == list(range(1, rounds + 3))
    assert all(c.seq is not None for c in chronicle.chapters)
    assert [c.seq for c in chronicle.chapters] == sorted(c.seq for c in chronicle.chapters)


def test_at_a_glance_names_the_winner_the_turning_point_and_the_cost():
    glance = {g.label: g.value for g in story("epic", "en", cost_micro_eur=49396).glance}

    assert glance["Last one standing"] == "glm-flash"
    assert glance["Duration"] == "10 rounds"
    assert "coin flip" in glance["The turning point"]
    assert glance["Luckiest soul"].startswith("gemini-flash-lite")
    assert glance["Cost of the saga"] == "EUR 0.0494"
    assert "Cost of the saga" not in {g.label for g in story("epic", "en").glance}
    assert "no 1 lies" not in " ".join(glance.values())
    assert "## At a glance" in to_markdown(story("epic", "en"))


def test_the_story_has_the_facts_who_bluffed_who_called_what_was_shown_and_who_fell():
    text = "\n".join(c.text for c in story("epic", "en").chapters)

    assert "llama-scout" in text and "4th" in text  # the first one out
    assert "ace, ace" in text  # a reveal, in words
    assert "Three kings, for the crown!" in text  # a quote, verbatim
    assert re.search(r"live one|thunderclap", text)  # a live shot
    assert "1 in 2" in text  # the coin flip
    assert "1. glm-flash, 2. gemini-flash-lite, 3. deepseek-flash, 4. llama-scout" in text


def test_german_has_german_cards_and_places():
    text = "\n".join(c.text for c in story("epic", "de").chapters)

    assert "Ass" in text and "König" in text and "Dame" in text
    assert "Platz 4" in text and "1 zu 2" in text
    assert "king" not in text.replace("Three kings", "").lower() or "König" in text


def test_the_key_moments_say_where_to_jump_in_the_replay():
    moments = story("epic", "en").key_moments

    assert {"reveal", "trigger", "eliminated", "duel"} <= {m["kind"] for m in moments}
    for moment in moments:
        assert EVENTS[moment["seq"]].type in {
            "cards_revealed",
            "trigger_pulled",
            "players_eliminated",
            "round_started",
            "shooters_chosen",
            "cards_played",
        }
        assert moment["players"] and moment["phase"] in ("round", "prologue", "epilogue")


def test_the_same_log_tells_the_same_story_and_another_seed_another_one():
    first = to_markdown(story("novel", "en"))
    start = EVENTS[0].model_copy(update={"data": {**EVENTS[0].data, "seed": 99}})

    assert first == to_markdown(story("novel", "en"))
    assert first != to_markdown(story("novel", "en", events=[start, *EVENTS[1:]]))


@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize("style", STYLES)
def test_every_template_variant_only_uses_fields_of_its_kind(style, lang):
    kinds = templates("liars_deck", lang)[style]["kinds"]

    assert set(kinds) == set(FIELDS), set(kinds) ^ set(FIELDS)
    for kind, variants in kinds.items():
        assert variants, (style, lang, kind)
        for variant in variants:
            used = {name for _, name, _, _ in string.Formatter().parse(variant) if name}
            assert used <= set(FIELDS[kind]), (style, lang, kind, used - set(FIELDS[kind]))
    assert len(kinds["round_starts"]) >= 4 and len(kinds["reveal_wrong"]) >= 4
    assert templates("liars_deck", lang)[style]["again"]


@pytest.mark.parametrize("seed", range(1, 9))
def test_real_bot_matches_tell_without_a_seat_id_or_a_repeated_sentence(seed):
    settings = {"variant": "devil_card"} if seed % 2 == 0 else {}
    events = bot_events(seed, players=2 + seed % 3, settings=settings)
    names = display_names({p: ("bot", p) for p in events[0].data["players"]})

    for lang in LANGS:
        for style in STYLES:
            chronicle = tell(events, style=style, lang=lang, names=names)
            text = all_text(chronicle)
            assert not SEAT.search(text), (seed, style, lang, SEAT.findall(text))
            told = sentences(chronicle)
            assert not {s for s in told if told.count(s) > 1}, (seed, style, lang)
            assert chronicle.chapters[0].kind == "prologue"
            assert chronicle.chapters[-1].kind == "epilogue"


def test_the_devil_card_is_told_when_it_is_revealed():
    for seed in range(1, 40):
        events = bot_events(seed, players=4, settings={"variant": "devil_card"})
        if any(e.type == "cards_revealed" and e.data["devil"] for e in events):
            text = "\n".join(c.text for c in tell(events, names=NAMES | {}).chapters)
            assert "devil card" in text
            return
    pytest.skip("no bot match revealed the devil card in these seeds")


@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize("style", STYLES)
def test_golden_chronicle_of_the_real_example_match(style, lang):
    text = to_markdown(story(style, lang, cost_micro_eur=49396))
    path = GOLDEN / f"liars_deck_{style}_{lang}.md"
    if os.environ.get("UPDATE_GOLDEN"):
        path.parent.mkdir(exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")

    assert path.exists(), f"{path.name} is missing; run with UPDATE_GOLDEN=1"
    assert text == path.read_text(encoding="utf-8"), (
        f"{path.name} changed; UPDATE_GOLDEN=1 if intended"
    )
