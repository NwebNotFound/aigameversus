"""A narrator with a model: retells a game's `narration` events in a livelier voice.

Games emit narration with the facts and a template text (see
`games/werewolf/narrator.py`), so they never call a model. A game master that
has a model can pass each narration event here; without one, or whenever the
model fails or answers off-script, the template text stands.

    text = await retell(event.data, model_call, style="epic")
"""

import json
from collections.abc import Mapping
from typing import Any

from arena.agents.model import ModelCall, ModelError

MAX_WORDS = 60
STYLES = ("plain", "epic", "news", "sports")

_LANGUAGE = {"de": "German", "en": "English"}


def prompt(narration: Mapping[str, Any], style: str) -> list[dict[str, str]]:
    """The messages for one retelling. The facts go in as JSON data, never as instructions."""
    language = _LANGUAGE.get(narration.get("language", "en"), "English")
    system = (
        "You are the narrator of a game watched by an audience. Retell the moment below "
        f"in {language}, in one or two sentences, at most {MAX_WORDS} words, in a {style} "
        "style. Keep every fact exactly: who, which role, how many. Invent nothing that "
        "changes the game, and reveal nothing that is not in the facts. Answer with the "
        "text only."
    )
    facts = json.dumps(
        {"moment": narration["key"], "facts": narration["data"], "plain_text": narration["text"]},
        ensure_ascii=False,
    ).replace("<", "\\u003c")
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": f"<moment>\n{facts}\n</moment>"},
    ]


async def retell(narration: Mapping[str, Any], call: ModelCall, *, style: str = "plain") -> str:
    """The model's retelling, or the template text if the model fails or overruns."""
    if style not in STYLES:
        raise ValueError(f"style must be one of {', '.join(STYLES)}")
    try:
        reply = await call(prompt(narration, style), [])
    except ModelError:
        return narration["text"]
    text = (reply.text or "").strip()
    if not text or len(text.split()) > MAX_WORDS:
        return narration["text"]
    return text
