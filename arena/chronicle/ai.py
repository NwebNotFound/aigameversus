"""An AI-written chronicle: a model retells the template chronicle, fact-checked chapter by chapter.

The template chronicle (`tell`) holds the facts of a finished match, already right. The model
gets those chapters and rewrites their words in the style and language asked, in one call. It
may add no fact: every player name, number, card and role word in a rewritten chapter must
also be in that chapter's template text, else the chapter keeps its template text and says
why (`checks`). The result says it is AI-written and which model wrote it (D-140).
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from functools import cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from arena.agents.model import Message, ModelCall
from arena.chronicle import Chronicle

PROMPT_VERSION = "chronicle-ai-1"
TOOL = "write_chronicle"
LONGEST = 3.0  # a rewritten chapter may be at most this many times its template's length
ROLES_DIR = Path(__file__).resolve().parents[2] / "games" / "werewolf" / "roles"
# Words that carry facts in the games' stories, in English and German; a rewrite may use one
# only where the template chapter has it too. Names and numbers are checked the same way.
CARD_WORDS = {
    "king", "kings", "queen", "queens", "ace", "aces", "jack", "jacks", "joker", "jokers",
    "könig", "könige", "dame", "damen", "ass", "asse", "bube", "buben",
    "flush", "straight", "pair", "pairs", "trips", "quads", "full house", "royal",
    "drilling", "vierling", "straße", "paar",
}  # fmt: skip
NUMBER_WORDS = {
    "zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
    "eleven", "twelve", "once", "twice", "first", "second", "third", "fourth", "fifth",
    "null", "eins", "zwei", "drei", "vier", "fünf", "sechs", "sieben", "acht", "neun", "zehn",
    "elf", "zwölf", "einmal", "zweimal", "erste", "zweite", "dritte", "vierte", "fünfte",
}  # fmt: skip
STYLE_WORDS = {
    "epic": "an epic saga: grand, solemn, heroic",
    "news": "a newspaper report: factual, clear, the key facts first",
    "sports": "a sports commentary: lively, fast, dramatic",
    "novel": "a short novel: vivid, close to the players' thoughts",
}


class ChapterCheck(BaseModel):
    number: int
    ai: bool = Field(description="True: the rewritten text is used; False: the template's")
    reason: str | None = None


class AiChronicle(BaseModel):
    """A chronicle in a model's words, labelled as such."""

    ai_written: bool = True
    label: str = "AI-written retelling, fact-checked against the match log"
    model: str
    prompt_version: str = PROMPT_VERSION
    chronicle: Chronicle
    checks: list[ChapterCheck]


@cache
def role_words() -> frozenset[str]:
    words: set[str] = set()
    for path in ROLES_DIR.glob("*.yaml"):
        role = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for key in ("id", "name", "name_de", "name_en"):
            value = role.get(key)
            if isinstance(value, str):
                words.add(value.replace("_", " ").lower())
    words |= {"werewolf", "werewolves", "wolf", "wolves", "villager", "villagers", "werwolf"}
    return frozenset(words)


@cache
def civ_words() -> frozenset[str]:
    """Units, buildings, treaties and resources of Throne of Tokens, in English and German."""
    from games.civ.data_loader import load_civ_data

    data = load_civ_data()
    words = {"food", "wood", "iron", "gold", "nahrung", "holz", "eisen"}
    for table in (data.units, data.buildings, data.treaties):
        for item in table.values():
            for name in (item.id.replace("_", " "), item.name, item.name_de):
                words |= {name.lower(), f"{name.lower()}s"}  # and the plain English plural
    return frozenset(words)


def _numbers(text: str) -> set[str]:
    return set(re.findall(r"\d+(?:[.,]\d+)?", text))


def _words(text: str, vocabulary: set[str] | frozenset[str]) -> set[str]:
    low = text.lower()
    return {w for w in vocabulary if re.search(rf"(?<!\w){re.escape(w.lower())}(?!\w)", low)}


def check_chapter(rewritten: str, template: str, names: list[str]) -> str | None:
    """Why a rewritten chapter may not replace its template, or None if it may."""
    if not rewritten.strip():
        return "empty"
    if len(rewritten) > LONGEST * max(len(template), 80):
        return "much longer than the facts it retells"
    if extra := _words(rewritten, set(names)) - _words(template, set(names)):
        return f"names not in the chapter: {', '.join(sorted(extra))}"
    if extra := _numbers(rewritten) - _numbers(template):
        return f"numbers not in the chapter: {', '.join(sorted(extra))}"
    if extra := _words(rewritten, NUMBER_WORDS) - _words(template, NUMBER_WORDS):
        return f"numbers not in the chapter: {', '.join(sorted(extra))}"
    vocabulary = CARD_WORDS | role_words() | civ_words()
    if extra := _words(rewritten, vocabulary) - _words(template, vocabulary):
        return f"cards or roles not in the chapter: {', '.join(sorted(extra))}"
    return None


def tool_schema() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": TOOL,
            "description": "The retold chronicle: one text per chapter, by its number.",
            "parameters": {
                "type": "object",
                "properties": {
                    "chapters": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "number": {"type": "integer"},
                                "text": {"type": "string"},
                            },
                            "required": ["number", "text"],
                        },
                    }
                },
                "required": ["chapters"],
            },
        },
    }


def messages(chronicle: Chronicle, style: str, lang: str) -> list[Message]:
    language = {"en": "English", "de": "German"}[lang]
    facts = {
        "game": chronicle.game,
        "title": chronicle.title,
        "chapters": [
            {"number": c.number, "title": c.title, "text": c.text} for c in chronicle.chapters
        ],
    }
    system = (
        f"You retell a finished game for spectators as {STYLE_WORDS[style]}, in {language}. "
        "Rewrite the words of each chapter; keep its facts exactly. Use only what a chapter "
        "says: no new player, number, card, role or event, and keep every name as written. "
        f"Call {TOOL} once with one text per chapter, numbered as given."
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(facts, ensure_ascii=False)},
    ]


async def retell(
    chronicle: Chronicle,
    style: str,
    lang: str,
    names: Mapping[str, str],
    call: ModelCall,
    model: str,
) -> AiChronicle:
    """One model call; each chapter checked against its template, kept where it fails."""
    reply = await call(messages(chronicle, style, lang), [tool_schema()])
    written: dict[int, str] = {}
    problem = None
    if not reply.tool_calls or reply.tool_calls[0].name != TOOL:
        problem = "the model did not call write_chronicle"
    else:
        try:
            body = json.loads(reply.tool_calls[0].arguments)
            for item in body.get("chapters", []):
                if isinstance(item, dict) and isinstance(item.get("text"), str):
                    written[int(item["number"])] = item["text"]
        except (ValueError, TypeError, AttributeError):
            problem = "the model's chapters were not readable JSON"
    known = sorted({*names.values(), *names.keys()}, key=len, reverse=True)
    chapters, checks = [], []
    for chapter in chronicle.chapters:
        text = written.get(chapter.number)
        reason = problem or (
            "no text for this chapter" if text is None else check_chapter(text, chapter.text, known)
        )
        ok = reason is None
        chapters.append(chapter.model_copy(update={"text": text if ok else chapter.text}))
        checks.append(ChapterCheck(number=chapter.number, ai=ok, reason=reason))
    told = chronicle.model_copy(update={"chapters": chapters, "style": style, "lang": lang})
    return AiChronicle(model=model, chronicle=told, checks=checks)
