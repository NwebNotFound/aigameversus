"""The AI-written chronicle: a fake model retells the template chronicle, checked per chapter."""

import asyncio
import json

import pytest

from arena.agents.mock_llm import MockLLM, tool_call
from arena.agents.model import ModelReply
from arena.agents.random_bot import random_bots
from arena.chronicle import tell
from arena.chronicle.ai import TOOL, check_chapter, retell
from arena.engine.match import Match
from arena.games import load_games

NAMES = ["Ada", "Bo", "Cy", "p1", "p2", "p3"]


def finished(game="liars_deck", players=3, seed=5):
    plugin = load_games()[game]
    seats = [f"p{i}" for i in range(1, players + 1)]
    match = Match(plugin, random_bots(plugin, seats, seed), seed=seed, settings={})
    asyncio.run(match.run())
    return match.events


@pytest.mark.parametrize(
    ("rewrite", "says"),
    [
        ("Ada played two kings and Bo called it.", None),  # the same facts, other words
        ("Ada played two kings and Cy called it.", "names not in the chapter: Cy"),
        ("Ada played three kings and Bo called it.", "numbers not in the chapter: three"),
        ("Ada played 3 kings and Bo called it.", "numbers not in the chapter: 3"),
        ("Ada played two queens and Bo called it.", "cards or roles not in the chapter: queens"),
        (
            "The seer Ada played two kings and Bo called it.",
            "cards or roles not in the chapter: seer",
        ),
        ("", "empty"),
        ("Ada " * 400, "much longer"),
    ],
)
def test_a_rewrite_may_change_words_but_add_no_name_number_card_or_role(rewrite, says):
    template = "Ada played two kings and Bo called it."

    reason = check_chapter(rewrite, template, NAMES)

    assert (reason is None) if says is None else says in reason


def echo(transform=lambda number, text: text):
    """A fake model that returns every chapter, transformed, through the tool."""

    def answer(messages, tools):
        chapters = json.loads(messages[1]["content"])["chapters"]
        written = [
            {"number": c["number"], "text": transform(c["number"], c["text"])} for c in chapters
        ]
        return tool_call(TOOL, {"chapters": written})

    return MockLLM(answer)


def test_a_faithful_retelling_is_used_and_labelled_ai_written():
    story = tell(finished(), style="news", lang="en")

    told = asyncio.run(
        retell(story, "news", "en", {}, echo(lambda n, t: f"In short: {t}"), "glm-flash")
    )

    assert told.ai_written and "AI-written" in told.label and told.model == "glm-flash"
    assert all(check.ai for check in told.checks)
    assert all(c.text.startswith("In short: ") for c in told.chronicle.chapters)
    assert [c.number for c in told.chronicle.chapters] == [c.number for c in story.chapters]


def test_a_chapter_that_invents_a_fact_keeps_its_template_text():
    story = tell(finished(), style="epic", lang="en")
    first = story.chapters[0].number

    def invent(number, text):
        return f"{text} Then 99 jokers fell from the sky." if number == first else text

    told = asyncio.run(retell(story, "epic", "en", {}, echo(invent), "glm-flash"))

    check = next(c for c in told.checks if c.number == first)
    assert not check.ai and "numbers not in the chapter: 99" in check.reason
    assert told.chronicle.chapters[0].text == story.chapters[0].text  # the template's facts
    assert all(c.ai for c in told.checks if c.number != first)


def test_an_answer_without_the_tool_keeps_every_template_chapter():
    story = tell(finished("poker", 3, 2), style="epic", lang="en")

    told = asyncio.run(
        retell(story, "epic", "en", {}, MockLLM(ModelReply(text="Once upon a time")), "m")
    )

    assert not any(c.ai for c in told.checks)
    assert [c.text for c in told.chronicle.chapters] == [c.text for c in story.chapters]
    assert told.checks[0].reason == "the model did not call write_chronicle"
