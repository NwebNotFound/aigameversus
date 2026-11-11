"""Real models through LiteLLM. Nothing else in the project talks to a model provider."""

import os
from typing import Any

from arena.agents.model import Message, ModelError, ModelReply, ToolCall

_RETRYABLE_STATUS = {408, 409, 429}  # besides every 5xx and failures without a status


class LiteLLMModel:
    """A ModelCall for one model in LiteLLM's naming, e.g. `openrouter/<vendor>/<model>`.

    LiteLLM reads the provider's API key from the environment. Every call can
    cost money: tests and CI use the mock LLM instead.
    """

    def __init__(self, model: str):
        self._model = model

    async def __call__(self, messages: list[Message], tools: list[dict[str, Any]]) -> ModelReply:
        litellm = _litellm()
        try:
            response = await litellm.acompletion(
                model=self._model,
                messages=messages,
                tools=tools,
                num_retries=0,  # the agent runner retries, with its own backoff
            )
            message = response.choices[0].message
            return ModelReply(
                text=message.content,
                tool_calls=tuple(
                    ToolCall(call.function.name, call.function.arguments)
                    for call in message.tool_calls or ()
                ),
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
    return litellm
