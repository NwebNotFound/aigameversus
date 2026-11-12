import asyncio
import re

import pytest

from arena.agents.random_bot import random_bots
from arena.chronicle import (
    LANGS,
    STYLES,
    Chapter,
    ChronicleError,
    Narrator,
    TemplateNarrator,
    tell,
    to_markdown,
)
from arena.chronicle.text import FIELDS, KINDS, MORE, TEXT
from arena.engine.match import Match
from arena.engine.types import Event, EventSource
from games.liars_deck.plugin import LiarsDeck
from games.poker.plugin import Poker
from games.werewolf.plugin import Werewolf


def game(type, data):
    return Event(source=EventSource.GAME, type=type, data=data)


def engine(type, data, visible_to=None):
    return Event(source=EventSource.ENGINE, type=type, data=data, visible_to=visible_to)


def started(name, players):
    data = {"game": name, "version": "1", "players": players, "settings": {}, "seed": 1}
    return engine("match_started", data, visible_to=())


FINISHED = engine("match_finished", {"placements": []})


def bet(player, kind, street, to, added):
    data = {"player": player, "kind": kind, "street": street, "to": to, "added": added}
    return game("bet_action", data)


def revealed(player, cards, honest):
    data = {"player": player, "cards": cards, "honest": honest, "devil": False}
    return game("cards_revealed", data)


def liars_log():
    return [
        started("liars_deck", ["p1", "p2"]),
        game("round_started", {"round": 1, "table_card": "king", "starter": "p1", "hand_size": 5,
                               "players": ["p1", "p2"]}),
        game("cards_played", {"player": "p1", "count": 2}),
        game("liar_called", {"caller": "p2", "target": "p1", "automatic": False}),
        revealed("p1", ["Q1", "K2"], False),
        game("trigger_pulled", {"player": "p1", "pull": 1, "live": True}),
        game("match_over", {"winner": "p2"}),
        FINISHED,
    ]  # fmt: skip


def test_a_hand_built_liars_deck_log_becomes_one_chapter_with_the_facts_in_it():
    story = tell(liars_log(), style="epic", lang="en", names={"p1": "Ada", "p2": "Basil"})

    assert story.game == "liars_deck" and len(story.chapters) == 1
    text = story.chapters[0].text
    assert "Ada laid 2 card(s)" in text
    assert "Basil rose and named Ada a liar" in text
    assert "Queen 1, King 2" in text  # the hidden cards, told after the match
    assert "Ada pulled the trigger" in text and "Basil" in text.split("trigger")[-1]


def test_names_default_to_the_player_ids_and_german_uses_german_words():
    text = tell(liars_log(), style="news", lang="de").chapters[0].text

    assert "p2 ruft p1 einen Lügner" in text
    assert "Dame 1, König 2" in text


def test_a_log_of_a_match_that_is_not_over_is_refused():
    with pytest.raises(ChronicleError, match="not over"):
        tell(liars_log()[:-1])


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [({"style": "tabloid"}, "unknown style"), ({"lang": "fr"}, "unknown language")],
)
def test_unknown_style_or_language_is_refused(kwargs, message):
    with pytest.raises(ChronicleError, match=message):
        tell(liars_log(), **kwargs)


def test_a_game_without_a_chronicle_is_refused():
    log = [started("toy", ["p1"]), FINISHED]

    with pytest.raises(ChronicleError, match="no chronicle for 'toy'"):
        tell(log)


def test_the_poker_hand_tells_streets_raises_showdown_and_award():
    shown = {"player": "p2", "cards": ["As", "Ad"], "hand": "three_of_a_kind"}
    log = [
        started("poker", ["p1", "p2"]),
        game("hand_started", {"hand": 1, "button": "p1", "players": ["p1", "p2"], "big_blind": 20}),
        bet("p2", "raise", "preflop", 60, 50),
        bet("p1", "call", "preflop", 60, 40),
        game("street_started", {"street": "flop", "order": [], "cards": ["Ah", "Kd", "2c"]}),
        bet("p2", "all_in", "flop", 500, 440),
        game("showdown", {"hands": [shown]}),
        game("pot_awarded", {"amount": 120, "eligible": ["p2"], "shares": {"p2": 120}}),
        game("players_eliminated", {"players": ["p1"], "started_with": [0]}),
        game("match_over", {"reason": "last_player", "winner": "p2"}),
        FINISHED,
    ]  # fmt: skip

    text = tell(log, style="sports", lang="en").chapters[0].text

    assert "raises to 60" in text and "ALL IN from p2" in text
    assert "The flop is out: Ah Kd 2c" in text
    assert "p2 (three of a kind: As Ad)" in text
    assert "p2 takes down the pot of 120" in text
    assert "p1 is out of chips" in text and "p2 wins it all" in text


def test_every_style_and_language_has_every_kind_and_the_fields_it_needs():
    for lang in LANGS:
        for style in STYLES:
            templates = TEXT[lang][style]
            assert len(templates) == len(KINDS), (lang, style)
            for kind, template in zip(KINDS, templates, strict=True):
                used = set(re.findall(r"{(\w+)}", template))
                assert used <= set(FIELDS[kind]), (lang, style, kind, used)


def bot_events(plugin, players, seed):
    match = Match(
        plugin, random_bots(plugin, [f"p{i}" for i in range(1, players + 1)], seed), seed=seed
    )
    asyncio.run(match.run())
    return match.events


GAMES = [("liars_deck", LiarsDeck, 3), ("poker", Poker, 3), ("werewolf", Werewolf, 8)]


@pytest.mark.parametrize(("name", "plugin", "players"), GAMES)
def test_every_style_and_language_renders_a_real_bot_match_without_leftovers(name, plugin, players):
    events = bot_events(plugin(), players, 4)

    for lang in LANGS:
        for style in STYLES:
            story = tell(events, style=style, lang=lang)
            markdown = to_markdown(story)
            assert story.chapters and all(c.text.strip() for c in story.chapters)
            assert "{" not in markdown and "}" not in markdown, (lang, style)
            boxes = 1 if story.glance else 0  # the "At a glance" box has a heading too
            assert markdown.startswith("# ")
            assert markdown.count("\n## ") == len(story.chapters) + boxes


@pytest.mark.parametrize(("name", "plugin", "players"), GAMES)
def test_the_same_log_gives_the_same_chronicle_and_other_seeds_other_stories(name, plugin, players):
    first = to_markdown(tell(bot_events(plugin(), players, 6)))

    assert first == to_markdown(tell(bot_events(plugin(), players, 6)))
    assert first != to_markdown(tell(bot_events(plugin(), players, 7)))


def test_chapters_follow_the_rounds_hands_and_nights_of_the_log():
    for seed in range(1, 4):
        ld = bot_events(LiarsDeck(), 3, seed)
        assert len(tell(ld).chapters) == sum(e.type == "round_started" for e in ld)
        pk = bot_events(Poker(), 3, seed)
        assert len(tell(pk).chapters) == sum(e.type == "hand_started" for e in pk)


def test_the_key_moments_of_a_real_liars_deck_match_are_all_in_the_story():
    for seed in range(1, 6):
        events = bot_events(LiarsDeck(), 3, seed)
        reveals = [e for e in events if e.type == "cards_revealed"]
        shots = [e for e in events if e.type == "trigger_pulled"]
        text = " ".join(c.text for c in tell(events, style="epic").chapters)

        assert text.count("liar") >= len(reveals)
        assert text.count("pulled the trigger") == len(shots)
        assert text.count("left the table forever") == sum(e.data["live"] for e in shots)


def test_a_narrator_can_be_swapped_without_a_model():
    class Shouting(TemplateNarrator):
        def tell(self, beats, style, lang, names):
            return super().tell(beats, style, lang, names).upper()

    story = tell(liars_log(), narrator=Shouting())

    assert story.chapters[0].text.isupper()
    assert issubclass(Shouting, Narrator) and Chapter.model_fields["beats"]


@pytest.mark.parametrize(
    ("number", "title"),
    [(1, "1st"), (2, "2nd"), (3, "3rd"), (4, "4th"), (11, "11th"), (12, "12th"), (21, "21st")],
)
def test_epic_chapter_titles_count_in_good_english(number, title):
    assert title in TemplateNarrator().chapter_title("round", number, "epic", "en")


def test_the_poker_hand_limit_names_the_chip_leader():
    standings = [{"player": "p2", "rank": 1}, {"player": "p1", "rank": 2}]
    log = [
        started("poker", ["p1", "p2"]),
        game("hand_started", {"hand": 1, "button": "p1", "players": ["p1", "p2"], "big_blind": 20}),
        game("match_over", {"reason": "hand_limit", "winner": None}),
        engine("match_finished", {"placements": standings}),
    ]

    for lang in LANGS:
        for style in STYLES:
            text = tell(log, style=style, lang=lang).chapters[0].text
            assert "p2" in text.split("p1")[-1] and "niemand" not in text and "nobody" not in text


def test_the_extra_templates_use_known_fields():
    for lang in LANGS:
        for style in STYLES:
            for kind, template in MORE[lang][style].items():
                assert set(re.findall(r"{(\w+)}", template)) <= set(FIELDS[kind])
