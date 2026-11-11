"""Help for people who watch a game and have never played it: "Rules in 30 seconds" and a glossary.

Stored as YAML next to the game, in `games/<game>/viewer/`, one pair per language:

    rules_30s.<lang>.yaml   title and 6 to 10 short lines
    glossary.<lang>.yaml    8 to 12 terms with a plain explanation

`GET /games/{id}/viewer-help?lang=` serves them. Plain words, no jargon without an
explanation, and the same number of lines and terms in every language.
"""

from importlib import resources

import yaml
from pydantic import BaseModel, ConfigDict, Field

LANGUAGES = ("en", "de")
MIN_LINES, MAX_LINES = 6, 10
MIN_TERMS, MAX_TERMS = 8, 12


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Rules30(_Strict):
    title: str = Field(min_length=3, max_length=60)
    lines: list[str] = Field(min_length=MIN_LINES, max_length=MAX_LINES)


class Term(_Strict):
    term: str = Field(min_length=2, max_length=40)
    meaning: str = Field(min_length=10, max_length=220)


class Glossary(_Strict):
    terms: list[Term] = Field(min_length=MIN_TERMS, max_length=MAX_TERMS)


class ViewerHelp(BaseModel):
    game: str
    lang: str
    title: str
    lines: list[str]
    glossary: list[Term]


MAX_LINE = 200  # a line a viewer reads at a glance


def _read(game: str, name: str) -> dict | None:
    folder = resources.files(f"games.{game}").joinpath("viewer")
    path = folder.joinpath(name)
    if not path.is_file():
        return None
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def load_viewer_help(game: str, lang: str) -> ViewerHelp | None:
    """The help of a game in a language; None if the game has none in that language."""
    rules, glossary = _read(game, f"rules_30s.{lang}.yaml"), _read(game, f"glossary.{lang}.yaml")
    if rules is None or glossary is None:
        return None
    rules, glossary = Rules30(**rules), Glossary(**glossary)
    for line in rules.lines:
        if len(line) > MAX_LINE:
            raise ValueError(f"{game}/{lang}: a line is longer than {MAX_LINE} characters: {line}")
    return ViewerHelp(
        game=game, lang=lang, title=rules.title, lines=rules.lines, glossary=glossary.terms
    )
