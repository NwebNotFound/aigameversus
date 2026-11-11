"""The model-call boundary: what goes to a model and what comes back.

Everything on the arena side of this boundary (prompts, parsing, retries) is
the same for a real model and for the mock LLM.
"""

from dataclasses import dataclass
from typing import Any, Protocol

Message = dict[str, str]  # {"role": "system" | "user", "content": ...}


@dataclass(frozen=True)
class ToolCall:
    name: str
    arguments: str  # as the model wrote them: JSON text, not parsed yet


@dataclass(frozen=True)
class Usage:
    """The tokens a call was billed for, as the provider counted them."""

    input_tokens: int
    output_tokens: int
    reasoning_tokens: int | None = None  # the part of the output spent thinking, if reported


@dataclass(frozen=True)
class ModelReply:
    text: str | None = None
    tool_calls: tuple[ToolCall, ...] = ()
    usage: Usage | None = None  # None: the provider did not say
    cut_off: bool = False  # the answer ran into the output limit before it was finished


RATE_LIMITED = "RateLimitError"  # the reason of a call the provider refused: too many requests


class ModelError(Exception):
    """A model call failed. `retryable` says whether trying again can help.

    `reason` is the kind of failure in a word or two. It may end up in logs
    and in the event log, so it never holds a key, a prompt or a provider message.
    """

    def __init__(self, reason: str, *, retryable: bool = True):
        super().__init__(reason)
        self.reason = reason
        self.retryable = retryable


class ModelCall(Protocol):
    """Sends one prompt with the allowed tools to a model and returns its answer.

    Raises ModelError when the call fails.
    """

    async def __call__(
        self, messages: list[Message], tools: list[dict[str, Any]]
    ) -> ModelReply: ...
