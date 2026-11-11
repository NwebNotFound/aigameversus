"""Viewer help ("Rules in 30 seconds" and a glossary): every game that is played has it, in every
language, in the same shape, and nothing in it names a seat or another game's trademark."""

import re

import pytest
from pydantic import ValidationError

from arena import viewer_help
from arena.games import load_games
from arena.viewer_help import LANGUAGES, load_viewer_help

# No help for the reference game; Throne of Tokens gets its own when its plugin ships.
EXEMPT = {"toy", "civ"}
GAMES = sorted(set(load_games()) - EXEMPT)


@pytest.mark.parametrize("game", GAMES)
@pytest.mark.parametrize("lang", LANGUAGES)
def test_every_played_game_has_help_in_every_language(game, lang):
    found = load_viewer_help(game, lang)

    assert found is not None, f"games/{game}/viewer/ has no {lang} files"
    assert found.game == game and found.lang == lang
    assert viewer_help.MIN_LINES <= len(found.lines) <= viewer_help.MAX_LINES
    assert viewer_help.MIN_TERMS <= len(found.glossary) <= viewer_help.MAX_TERMS


@pytest.mark.parametrize("game", GAMES)
def test_the_languages_have_the_same_shape(game):
    en, de = load_viewer_help(game, "en"), load_viewer_help(game, "de")

    assert len(en.lines) == len(de.lines)
    assert len(en.glossary) == len(de.glossary)
    assert en.title != de.title


@pytest.mark.parametrize("game", GAMES)
@pytest.mark.parametrize("lang", LANGUAGES)
def test_the_texts_are_clean(game, lang):
    found = load_viewer_help(game, lang)
    texts = [found.title, *found.lines] + [t for x in found.glossary for t in (x.term, x.meaning)]

    terms = [x.term.lower() for x in found.glossary]
    assert len(set(terms)) == len(terms), "a term is explained twice"
    for text in texts:
        assert text == text.strip() and "  " not in text, repr(text)
        assert not re.search(r"\bp\d\b", text), f"a seat id in: {text}"
        assert "liar's bar" not in text.lower()


def test_a_game_without_files_has_no_help_and_a_broken_file_is_refused(monkeypatch):
    assert load_viewer_help("toy", "en") is None

    broken = {"title": "x", "lines": ["only one line"]}
    monkeypatch.setattr(viewer_help, "_read", lambda game, name: broken)
    with pytest.raises(ValidationError):
        load_viewer_help("poker", "en")


def test_a_line_that_is_too_long_to_read_at_a_glance_is_refused(monkeypatch):
    long = {"title": "A title", "lines": ["word " * 50] * 6}
    terms = {"terms": [{"term": f"Term {i}", "meaning": "A plain explanation."} for i in range(8)]}
    monkeypatch.setattr(viewer_help, "_read", lambda game, name: long if "rules" in name else terms)

    with pytest.raises(ValueError, match="longer than"):
        load_viewer_help("poker", "en")
