"""The Werewolf chronicle: a recap built from facts, with display names, in four styles.

No seat id in the text (not even inside a quote), no sentence told twice, a different shape for
every style, the same log always the same story, and golden files for the real example match.
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
from arena.chronicle.compose import FIELDS, templates
from arena.chronicle.digest import QUOTE_WORDS, quote_of
from arena.engine.match import Match
from arena.engine.types import Event
from arena.transcript.common import display_names
from games.werewolf.plugin import Werewolf
from games.werewolf.selection import load_roles

ROOT = Path(__file__).resolve().parents[2]
GOLDEN = Path(__file__).parent / "golden"
SEAT = re.compile(r"\bp\d+\b", re.IGNORECASE)
EXAMPLE = json.loads((ROOT / "docs" / "examples" / "werewolf.json").read_text(encoding="utf-8"))
EVENTS = [Event(**e) for e in EXAMPLE["events"]]
NAMES = display_names({seat: ("model", model) for seat, model in EXAMPLE["seats"].items()})


def story(style="epic", lang="en", events=EVENTS, names=NAMES, **kwargs):
    return tell(events, style=style, lang=lang, names=names, **kwargs)


def all_text(chronicle) -> str:
    glance = [f"{g.label}: {g.value}" for g in chronicle.glance]
    parts = [chronicle.title, chronicle.glance_title, *glance]
    return "\n".join(parts + [f"{c.title}\n{c.text}" for c in chronicle.chapters])


def sentences(chronicle) -> list[str]:
    text = "\n".join(c.text for c in chronicle.chapters)
    return [s.strip("- ").strip() for s in re.split(r"(?<=[.!?…])\s+|\n+", text) if s.strip("- ")]


def bot_events(seed, players=8, settings=None):
    plugin = Werewolf()
    names = [f"p{i}" for i in range(1, players + 1)]
    match = Match(plugin, random_bots(plugin, names, seed), seed=seed, settings=settings or {})
    asyncio.run(match.run())
    return match.events


@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize("style", STYLES)
def test_no_seat_id_reaches_the_text_and_every_player_is_a_display_name(style, lang):
    chronicle = story(style, lang)
    text = all_text(chronicle)

    assert not SEAT.search(text), SEAT.findall(text)
    assert "{" not in text and "}" not in text
    for name in ("deepseek-flash", "mistral-small", "qwen-flash"):
        assert name in text


@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize("style", STYLES)
def test_no_sentence_is_told_twice_in_a_chronicle(style, lang):
    told = sentences(story(style, lang))

    repeated = {s for s in told if told.count(s) > 1}
    assert not repeated, repeated


@pytest.mark.parametrize("lang", LANGS)
def test_a_quote_is_marked_and_short(lang):
    for style in STYLES:
        text = "\n".join(c.text for c in story(style, lang).chapters)
        quotes = re.findall(r'"([^"]+)"', text)
        assert quotes, style
        for quote in quotes:
            assert len(quote.split()) <= QUOTE_WORDS + 1, quote


@pytest.mark.parametrize("lang", LANGS)
def test_the_styles_differ_in_structure_and_in_words(lang):
    told = {style: story(style, lang) for style in STYLES}

    assert len({c.title for c in told.values()}) == len(STYLES)
    assert len({tuple(ch.title for ch in c.chapters) for c in told.values()}) == len(STYLES)
    assert len({c.chapters[2].text for c in told.values()}) == len(STYLES)
    news, sports, novel, epic = (told[s] for s in ("news", "sports", "novel", "epic"))
    assert all(line.startswith("- ") for c in news.chapters for line in c.text.split("\n"))
    assert any("\n" in c.text for c in sports.chapters) and "- " not in sports.chapters[2].text[:2]
    assert any("\n\n" in c.text for c in novel.chapters)
    assert all("\n" not in c.text for c in epic.chapters)


@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize("style", STYLES)
def test_the_chapters_are_prologue_nights_days_and_epilogue(style, lang):
    chronicle = story(style, lang)

    kinds = [c.kind for c in chronicle.chapters]
    assert kinds == ["prologue", "night", "day", "night", "day", "epilogue"]
    assert [c.number for c in chronicle.chapters] == [1, 2, 3, 4, 5, 6]
    assert all(c.seq is not None for c in chronicle.chapters)
    assert chronicle.chapters[0].seq < chronicle.chapters[-1].seq


def test_at_a_glance_names_the_winner_the_turning_point_the_best_and_the_cost():
    chronicle = story("epic", "en", cost_micro_eur=15484)

    glance = {g.label: g.value for g in chronicle.glance}
    assert chronicle.glance_title == "At a glance"
    assert glance["Victor"] == "The wolves (deepseek-flash and gemini-flash-lite)"
    assert glance["Duration"] == "2 days"
    assert "mistral-small (Seer)" in glance["The turning point"]
    assert glance["Master of masks"].startswith("deepseek-flash")
    assert glance["Cost of the tale"] == "EUR 0.0155"
    assert "Cost of the tale" not in {g.label for g in story("epic", "en").glance}
    markdown = to_markdown(chronicle)
    assert "## At a glance" in markdown and "- **Victor:**" in markdown


def test_the_story_has_the_facts_who_accused_whom_why_the_claims_and_the_tallies():
    text = "\n".join(c.text for c in story("epic", "en").chapters)

    assert "llama-scout 7, qwen-flash 1" in text  # the tally
    assert re.search(r"no wolf at all but a Villager|an honest Villager", text)  # the wrong vote
    assert "Two rounds, no suspect, no observation" in text  # a vote's reason, verbatim
    assert "qwen-flash swore to be a Villager, but was in truth a Hunter" in text  # a lie
    assert "gemini-flash-lite as captain with 5 votes" in text
    assert "claude-haiku" in text and "the Witch" in text  # the first victim, with their role
    assert "Behind the masks" in text  # the epilogue reveals everyone


def test_the_key_moments_say_where_to_jump_in_the_replay():
    moments = story("epic", "en").key_moments

    kinds = [m["kind"] for m in moments]
    assert {"captain", "death", "execution", "claim_lie"} <= set(kinds)
    for moment in moments:
        assert EVENTS[moment["seq"]].type in {
            "captain_elected",
            "player_died",
            "vote_result",
            "message",
            "morning_started",
            "hunter_shot",
        }
        assert moment["players"] and "phase" in moment


def test_the_same_log_tells_the_same_story_and_another_seed_another_one():
    first = to_markdown(story("novel", "en"))
    start = EVENTS[0].model_copy(update={"data": {**EVENTS[0].data, "seed": 99}})

    assert first == to_markdown(story("novel", "en"))
    assert first != to_markdown(story("novel", "en", events=[start, *EVENTS[1:]]))


def test_names_are_used_only_as_given_and_a_match_not_over_is_refused():
    unnamed = story(names={})  # without names the seats are all there is: still no crash
    assert unnamed.chapters

    with pytest.raises(Exception, match="not over"):
        tell([e for e in EVENTS if e.type != "match_finished"], names=NAMES)


@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize("style", STYLES)
def test_every_template_variant_only_uses_fields_of_its_kind(style, lang):
    kinds = templates("werewolf", lang)[style]["kinds"]

    assert set(kinds) == set(FIELDS), set(kinds) ^ set(FIELDS)
    for kind, variants in kinds.items():
        assert variants, (style, lang, kind)
        for variant in variants:
            used = {name for _, name, _, _ in string.Formatter().parse(variant) if name}
            assert used <= set(FIELDS[kind]), (style, lang, kind, used - set(FIELDS[kind]))


def test_the_frequent_kinds_have_several_variants_in_every_style_and_language():
    for lang in LANGS:
        for style in STYLES:
            kinds = templates("werewolf", lang)[style]["kinds"]
            for kind in ("night_falls", "day_breaks", "vote_reason", "death_wolves"):
                assert len(kinds[kind]) >= 2, (style, lang, kind)
            assert len(kinds["vote_reason"]) >= 3 and len(kinds["death_wolves"]) >= 3


@pytest.mark.parametrize("seed", range(1, 7))
def test_real_bot_matches_of_every_role_tell_without_a_seat_id_or_a_repeated_sentence(seed):
    roles = {"roles": dict.fromkeys(load_roles(), 1)}
    events = bot_events(seed, players=16, settings=roles) if seed % 2 else bot_events(seed)
    start = events[0].data["players"]
    names = display_names({p: ("bot", p) for p in start})

    for lang in LANGS:
        for style in STYLES:
            chronicle = tell(events, style=style, lang=lang, names=names)
            text = all_text(chronicle)
            assert not SEAT.search(text), (seed, style, lang, SEAT.findall(text))
            assert chronicle.chapters[0].kind == "prologue"
            told = sentences(chronicle)
            assert not {s for s in told if told.count(s) > 1}, (seed, style, lang)


def test_a_quote_is_cut_at_a_clause_names_only_known_seats_and_is_short():
    seats = ["p1", "p2", "p3"]
    long = (
        "I really do not think that p2 is telling the truth about the night, because the story "
        "keeps changing every single time somebody asks a simple question about it."
    )

    cut = quote_of(long, seats)

    assert cut.endswith("…") and len(cut.split()) <= QUOTE_WORDS
    assert cut.split()[-1].rstrip("…") not in ("the", "a", "to")
    assert quote_of("p9 did it. Trust me.", seats, prefer_mention=True) is None  # not a seat here
    assert quote_of("   ", seats) is None
    assert quote_of("Short and sweet.", seats) == "Short and sweet."


@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize("style", STYLES)
def test_golden_chronicle_of_the_real_example_match(style, lang):
    text = to_markdown(story(style, lang, cost_micro_eur=15484))
    path = GOLDEN / f"werewolf_{style}_{lang}.md"
    if os.environ.get("UPDATE_GOLDEN"):
        path.parent.mkdir(exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")

    assert path.exists(), f"{path.name} is missing; run with UPDATE_GOLDEN=1"
    assert text == path.read_text(encoding="utf-8"), (
        f"{path.name} changed; UPDATE_GOLDEN=1 if intended"
    )
