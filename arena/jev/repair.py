"""Tier 2 of the move repair: which legal move did the model mean with its broken call?

The pipeline of one move (answer_repair "v2"):

0. the model is asked again with the engine's error (the engine's corrections);
1. a garbled but clear call is read deterministically (arena/agents/arguments.py, "v1");
2. if it is still refused, Jev chooses among the LEGAL moves the engine offers: the state
   is the tail of the model's own reasoning, its broken calls with the errors, and a short
   summary of what that player sees; nothing of anyone else's hidden state;
3. otherwise, and whenever Jev is unsure or fails, the random fallback (permanent).

Jev's pick is played only when its top probability reaches the threshold for that many
options (config/jev.yaml). Free text (speech) is never repaired: a tool whose required
argument is free text is not an option, and optional free text is dropped from a move.
"""

import json
from collections.abc import Callable, Mapping
from typing import Any

from arena.engine.types import Action, RepairOutcome, RepairRequest, ToolSpec
from arena.jev.client import ChoiceAnswer, JevClient, JevError
from arena.jev.config import JevConfig

QUESTION = "intended_move"
TEXT_FIELDS = {"text", "reason", "claim_text", "message", "speech"}


def _free_text(name: str, schema: Mapping[str, Any]) -> bool:
    """A string argument people write in, not one picked from a set (ids, targets, cards)."""
    kinds = schema.get("type")
    kinds = kinds if isinstance(kinds, list) else [kinds]
    if "string" not in kinds or "enum" in schema:
        return False
    return name in TEXT_FIELDS or schema.get("maxLength", 0) >= 100


def _wide(schema: Mapping[str, Any], limit: int) -> bool:
    """An integer argument with more values than Jev may be shown (a bet between bounds)."""
    low, high = schema.get("minimum"), schema.get("maximum")
    return (
        schema.get("type") == "integer"
        and isinstance(low, int)
        and isinstance(high, int)
        and high - low + 1 > limit
    )


def _tried(name: str, schema: Mapping[str, Any], attempts: list[dict[str, Any]]) -> int | None:
    """The one amount the model itself wrote for this argument in its broken calls, if one."""
    low, high = schema["minimum"], schema["maximum"]
    values = {
        value
        for attempt in attempts
        if isinstance(attempt.get("arguments"), dict)
        for value in [attempt["arguments"].get(name)]
        if isinstance(value, int) and not isinstance(value, bool) and low <= value <= high
    }
    return values.pop() if len(values) == 1 else None


def options_of(
    candidates: list[Action],
    tools: list[ToolSpec],
    limit: int,
    attempts: list[dict[str, Any]] | None = None,
) -> list[Action] | None:
    """The moves Jev may choose from: speech tools out, optional free text dropped, distinct.

    Nothing is guessed (D-123, research/JEV): an amount with more values than `limit` (a
    bet) is offered only as the one amount the model itself wrote in its broken calls; a
    move needing an amount the model did not write uniquely is not offered. The engine's
    random amounts never are.

    None when there are more distinct moves than `limit`: Jev then abstains instead of
    seeing a cut list.
    """
    specs = {tool.name: tool for tool in tools}
    cleaned: list[Action] = []
    seen: set[str] = set()
    for action in candidates:
        spec = specs.get(action.tool)
        if spec is None:
            continue
        properties = spec.parameters.get("properties", {})
        required = set(spec.parameters.get("required", []))
        if any(_free_text(name, properties.get(name, {})) for name in required):
            continue  # a move that is speech: never written by anyone but the model
        arguments = {
            name: value
            for name, value in action.arguments.items()
            if not _free_text(name, properties.get(name, {}))
        }
        for name in list(arguments):
            schema = properties.get(name, {})
            if _wide(schema, limit):
                amount = _tried(name, schema, attempts or [])
                if amount is None:
                    arguments = None  # no amount of the model's own: not an option
                    break
                arguments[name] = amount
        if arguments is None:
            continue
        move = Action(tool=action.tool, arguments=arguments)
        key = json.dumps([move.tool, move.arguments], sort_keys=True)
        if key not in seen:
            seen.add(key)
            cleaned.append(move)
    return cleaned if len(cleaned) <= limit else None


def describe(move: Action) -> str:
    arguments = ", ".join(
        f"{k}={json.dumps(v, ensure_ascii=False)}" for k, v in move.arguments.items()
    )
    return f"{move.tool}({arguments})"


def state_of(request: RepairRequest, config: JevConfig) -> dict[str, Any]:
    """What Jev reads: the player's own view and words only."""
    situation = request.summary or json.dumps(request.observation, ensure_ascii=False)
    return {
        "game": request.game,
        "player": request.player,
        "situation": situation[-config.situation_chars :] if config.situation_chars else "",
        "model_reasoning_end": (request.thought or "")[-config.reasoning_chars :]
        if config.reasoning_chars
        else "",
        "broken_calls": [
            {"tool": a.get("tool"), "arguments": a.get("arguments"), "error": a.get("error")}
            for a in request.attempts[-3:]
        ],
        "raw_calls": [raw[-500:] for raw in request.raw[-3:]],
        "task": "Which of the listed legal moves did this player mean with its broken call? "
        "Judge only the player's own reasoning and call; do not pick the best move.",
    }


class JevRepairer:
    """The Repairer of answer_repair "v2", on Jev's `choice` question."""

    def __init__(self, client_for: Callable[[str], JevClient], config: JevConfig):
        """`client_for(player)`: the Jev client to ask for that player's move (metered)."""
        self._client_for = client_for
        self._config = config
        self.samples = config.samples  # how many random legal moves the engine draws

    async def repair(self, request: RepairRequest, candidates: list[Action]) -> RepairOutcome:
        options = options_of(candidates, request.tools, self._config.max_options, request.attempts)
        if options is None:
            return RepairOutcome(action=None, reason="too_many_options")
        if not options:
            return RepairOutcome(action=None, reason="no_options")
        if len(options) == 1:
            # One option always gets probability 1: the threshold could not protect it, and
            # Jev would only ever confirm the one sampled move. The fallback plays.
            return RepairOutcome(action=None, reason="single_option", options=1)
        names = {f"m{i}": move for i, move in enumerate(options, start=1)}
        question = {
            QUESTION: {"type": "choice", "criteria": {k: describe(m) for k, m in names.items()}}
        }
        try:
            client = self._client_for(request.player)
            result = await client(state_of(request, self._config), question)
        except JevError as error:
            return RepairOutcome(action=None, reason=error.reason, options=len(options))
        answer = result.answers[QUESTION]
        assert isinstance(answer, ChoiceAnswer)  # checked by client.parse: choice = argmax
        pick, top = answer.choice, answer.probabilities[answer.choice]
        if top < self._config.threshold(len(options)):
            return RepairOutcome(
                action=None, reason="below_threshold", top_probability=top, options=len(options)
            )
        return RepairOutcome(
            action=names[pick], reason="accepted", top_probability=top, options=len(options)
        )
