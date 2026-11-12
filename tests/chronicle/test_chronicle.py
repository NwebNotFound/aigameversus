import asyncio

import pytest

from arena.agents.random_bot import random_bots
from arena.chronicle import LANGS, STYLES, ChronicleError, tell, to_markdown
from arena.engine.match import Match
from arena.engine.types import Event, EventSource
from games.civ.plugin import CivGame
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


def bot_events(plugin, players, seed):
    match = Match(
        plugin, random_bots(plugin, [f"p{i}" for i in range(1, players + 1)], seed), seed=seed
    )
    asyncio.run(match.run())
    return match.events


GAMES = [
    ("liars_deck", LiarsDeck, 3),
    ("poker", Poker, 3),
    ("werewolf", Werewolf, 8),
    ("civ", CivGame, 4),
]


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
