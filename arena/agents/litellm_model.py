"""Real models through LiteLLM. Nothing else in the project talks to a model provider."""

import logging
import os
from typing import Any

from arena.agents.model import Message, ModelError, ModelReply, ToolCall, Usage

_RETRYABLE_STATUS = {408, 409, 429}  # besides every 5xx and failures without a status


class LiteLLMModel:
    """A ModelCall for one model in LiteLLM's naming, e.g. `openrouter/<vendor>/<model>`.

    LiteLLM reads the provider's API key from the environment. Every call can
    cost money: matches get this class only through `Budget.model`, which
    counts the cost, and tests and CI use the mock LLM instead.
    """

    def __init__(self, model: str, *, max_output_tokens: int, reasoning_effort: str | None = None):
        self._model = model
        self._max_output_tokens = max_output_tokens
        # Reasoning is billed as output and counts against the output limit.
        self._options = {} if reasoning_effort is None else {"reasoning_effort": reasoning_effort}

    async def __call__(self, messages: list[Message], tools: list[dict[str, Any]]) -> ModelReply:
        litellm = _litellm()
        try:
            response = await litellm.acompletion(
                model=self._model,
                messages=messages,
                tools=tools,
                max_tokens=self._max_output_tokens,
                num_retries=0,  # the agent runner retries, with its own backoff
                **self._options,
            )
            choice = response.choices[0]
            message = choice.message
            usage = getattr(response, "usage", None)
            return ModelReply(
                # A model that only reasoned has said what it thinks there.
                text=message.content or getattr(message, "reasoning_content", None),
                tool_calls=tuple(
                    ToolCall(call.function.name, call.function.arguments)
                    for call in message.tool_calls or ()
                ),
                usage=(
                    None if usage is None else Usage(usage.prompt_tokens, usage.completion_tokens)
                ),
                cut_off=choice.finish_reason == "length",
            )
        except Exception as error:
            # Whatever fails here, in the provider or in an answer of an unexpected
            # shape, costs this player the call, never the match. Only the class
            # name travels on, and the original error is cut off: a provider
            # message can quote the request or part of a key.
            status = getattr(error, "status_code", None)
            retryable = not isinstance(status, int) or status in _RETRYABLE_STATUS or status >= 500
            raise ModelError(type(error).__name__, retryable=retryable) from None


def _litellm() -> Any:
    # Imported on first use: the import takes seconds, and outside offline mode
    # LiteLLM downloads a price list while it is imported. Offline mode only
    # stops such downloads of its own; calls to models are not affected.
    os.environ.setdefault("LITELLM_OFFLINE_MODE", "true")
    import litellm

    litellm.suppress_debug_info = True  # no help banners on stdout when a call fails
    # LiteLLM's own log is off: at debug level it prints whole requests and the
    # provider's error texts, which can quote a key. The arena logs what kind of
    # failure it was.
    logging.getLogger("LiteLLM").disabled = True
    return litellm
