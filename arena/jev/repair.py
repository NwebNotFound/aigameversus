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


def _amounts(name: str, schema: Mapping[str, Any], attempts: list[dict[str, Any]], tool: str):
    """The amounts offered for an integer argument: the bounds, the middle and what was tried."""
    low, high = schema.get("minimum"), schema.get("maximum")
    if low is None or high is None:
        return None
    values = {low, (low + high) // 2, high}
    for attempt in attempts:
        tried = (attempt.get("arguments") or {}).get(name)
        if attempt.get("tool") == tool and isinstance(tried, int) and low <= tried <= high:
            values.add(tried)
    return sorted(values)


def options_of(
    candidates: list[Action],
    tools: list[ToolSpec],
    limit: int,
    attempts: list[dict[str, Any]] | None = None,
) -> list[Action]:
    """The moves Jev may choose from: speech tools out, optional free text dropped, distinct.

    An integer argument with bounds (a bet) is offered as a few amounts: the minimum, the
    middle, the maximum and the amount the model itself tried, instead of random amounts.

    Kept in the order the engine sampled them, at most `limit`, with every tool that has a
    candidate represented before a tool gets a second one.
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
        variants = [arguments]
        for name, value in arguments.items():
            schema = properties.get(name, {})
            if schema.get("type") == "integer" and isinstance(value, int):
                amounts = _amounts(name, schema, attempts or [], action.tool)
                if amounts:
                    variants = [{**v, name: amount} for v in variants for amount in amounts]
        for variant in variants:
            move = Action(tool=action.tool, arguments=variant)
            key = json.dumps([move.tool, move.arguments], sort_keys=True)
            if key not in seen:
                seen.add(key)
                cleaned.append(move)
    by_tool: dict[str, list[Action]] = {}
    for move in cleaned:
        by_tool.setdefault(move.tool, []).append(move)
    picked: list[Action] = []
    depth = 0
    while len(picked) < limit and any(depth < len(moves) for moves in by_tool.values()):
        for moves in by_tool.values():
            if depth < len(moves) and len(picked) < limit:
                picked.append(moves[depth])
        depth += 1
    return picked


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
        if not options:
            return RepairOutcome(action=None, reason="no_options")
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
        assert isinstance(answer, ChoiceAnswer)  # checked by client.parse
        # The option with the highest probability, judged on that probability itself.
        pick = max(
            names, key=lambda name: (answer.probabilities.get(name, 0.0), name == answer.choice)
        )
        top = answer.probabilities.get(pick, 0.0)
        if top < self._config.threshold(len(options)):
            return RepairOutcome(
                action=None, reason="below_threshold", top_probability=top, options=len(options)
            )
        return RepairOutcome(
            action=names[pick], reason="accepted", top_probability=top, options=len(options)
        )
