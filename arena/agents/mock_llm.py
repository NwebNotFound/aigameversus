"""The mock LLM: a scripted stand-in for a model. Free, offline and repeatable."""

import asyncio
import json
from collections.abc import Callable
from typing import Any

from arena.agents.model import Message, ModelError, ModelReply, ToolCall, Usage


class _Hangs:
    pass


HANGS = _Hangs()  # script step: the call never returns, like a model that hangs

Policy = Callable[[list[Message], list[dict[str, Any]]], ModelReply]


class MockLLM:
    """A ModelCall that plays a script instead of asking a model.

    Every call takes the next step of the script; the last step repeats for
    all further calls. A step is one of:

    - a ModelReply: the answer;
    - a function `(messages, tools) -> ModelReply`: an answer made from the
      prompt, for a mock that plays by what it was shown;
    - a ModelError: raised, like a failed API call;
    - HANGS: the call never returns.

    `calls` holds the `(messages, tools)` of every call, to check what a model
    would have seen.
    """

    def __init__(self, *script: ModelReply | Policy | ModelError | _Hangs):
        if not script:
            raise ValueError("The script needs at least one step")
        self._script = list(script)
        self.calls: list[tuple[list[Message], list[dict[str, Any]]]] = []
        self.output_limits: list[int | None] = []  # the raised limit of each call, or None

    async def __call__(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]],
        *,
        max_output_tokens: int | None = None,
    ) -> ModelReply:
        self.calls.append((messages, tools))
        self.output_limits.append(max_output_tokens)
        step = self._script.pop(0) if len(self._script) > 1 else self._script[0]
        if isinstance(step, _Hangs):
            await asyncio.Event().wait()
        if isinstance(step, ModelError):
            raise step
        if isinstance(step, ModelReply):
            return step
        return step(messages, tools)


def tool_call(
    name: str, arguments: dict[str, Any], *, text: str | None = None, usage: Usage | None = None
) -> ModelReply:
    """The answer of a well-behaved model: one tool call, with thinking text if given."""
    return ModelReply(text=text, tool_calls=(ToolCall(name, json.dumps(arguments)),), usage=usage)
