"""The arguments of a model's tool call, read as kindly as is safe.

Models garble the format of a call they clearly meant: reasoning text around
the JSON, stray or mangled keys on a tool that takes none, a number sent as a
string. `read_arguments` repairs exactly these, and says what it repaired;
it never invents a value, and the engine still checks the result against the
tool's schema and the rules. Anything it cannot repair stays a problem for
the model to correct.
"""

import json
import re
from typing import Any

from arena.engine.types import ToolSpec

EXTRACTED_JSON = "extracted_json"  # the object was found inside other text
IGNORED_NON_OBJECT = "ignored_non_object"  # not an object, for a tool that takes no arguments
IGNORED_EXTRA_KEYS = "ignored_extra_keys"  # keys the tool does not have were dropped
COERCED_NUMBERS = "coerced_numbers"  # "40" became 40 where the schema wants a number
IGNORED_THOUGHT = "ignored_thought"  # a thought that was not text was dropped

SCAN_CHARS = 32_000  # of a call's text, searched for an object
SCAN_STARTS = 50  # "{" tried as the start of one

_INTEGER = re.compile(r"-?\d+")
_NUMBER = re.compile(r"-?(\d+\.?\d*|\.\d+)")


def read_arguments(
    raw: str, spec: ToolSpec | None, thought_key: str
) -> tuple[dict[str, Any] | None, list[str]]:
    """The arguments of a call to `spec` (None: a tool the turn does not offer), and the
    repairs made to get them. None when no object can be read."""
    repairs: list[str] = []
    arguments = _parse(raw)
    if arguments is None:
        arguments = _first_object(raw)
        if arguments is not None:
            repairs.append(EXTRACTED_JSON)
    properties = (spec.parameters.get("properties") or {}) if spec else None
    if not isinstance(arguments, dict):
        if spec is not None and not properties:
            return {}, [*repairs, IGNORED_NON_OBJECT]
        return None, repairs
    if thought_key in arguments and not isinstance(arguments[thought_key], str):
        del arguments[thought_key]
        repairs.append(IGNORED_THOUGHT)
    if properties is None:  # an unknown tool: the engine says so; nothing to repair against
        return arguments, repairs
    extra = [key for key in arguments if key not in properties and key != thought_key]
    if extra:
        for key in extra:
            del arguments[key]
        repairs.append(IGNORED_EXTRA_KEYS)
    coerced = False
    for key, value in arguments.items():
        number = _as_number(value, properties.get(key) or {})
        if number is not None:
            arguments[key] = number
            coerced = True
    if coerced:
        repairs.append(COERCED_NUMBERS)
    return arguments, repairs


def as_sent(raw: str) -> dict[str, Any] | None:
    """The arguments exactly as sent, if they are one JSON object (answer_repair "off")."""
    arguments = _parse(raw)
    return arguments if isinstance(arguments, dict) else None


def _parse(raw: str) -> Any:
    try:
        return json.loads(raw)
    except (ValueError, RecursionError, TypeError):
        return None


def _first_object(raw: str) -> dict[str, Any] | None:
    """The first JSON object in the text, from one of its first SCAN_STARTS "{".

    The decoder fails at once on garbage, and the scan is bounded, so a model that
    sends nothing but braces cannot hold up the server (this runs on its event loop).
    """
    if not isinstance(raw, str):
        return None
    text = raw[:SCAN_CHARS]
    decoder = json.JSONDecoder()
    start = text.find("{")
    for _ in range(SCAN_STARTS):
        if start == -1:
            return None
        try:
            found, _end = decoder.raw_decode(text, start)
        except (ValueError, RecursionError):
            found = None
        if isinstance(found, dict):
            return found
        start = text.find("{", start + 1)
    return None


def _as_number(value: Any, schema: dict[str, Any]) -> int | float | None:
    """`value` as the number its schema wants, if it is a string that spells exactly one."""
    if not isinstance(value, str):
        return None
    text = value.strip()
    kind = schema.get("type")
    if kind == "integer" and _INTEGER.fullmatch(text):
        return int(text)
    if kind == "number" and _NUMBER.fullmatch(text):
        return float(text)
    return None
