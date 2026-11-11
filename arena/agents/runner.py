"""The agent runner: a seat played by a language model."""

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from arena.agents.model import Message, ModelCall, ModelError, ModelReply
from arena.agents.prompt import THOUGHT, build_messages, tool_schemas
from arena.engine.plugin import GamePlugin
from arena.engine.types import Action, AgentError, Reply, TurnRequest

log = logging.getLogger(__name__)

MAX_RETRIES = 3  # further tries after a failed model call
BACKOFF_SECONDS = 1.0  # pause before the first retry; doubles with every retry


class ModelAgent:
    """Plays one seat by asking a model.

    Each turn it builds the prompt, calls the model and reads the answer: text
    is the private thought, the first tool call is the action. It does not
    judge the action; the engine does.

    A failed call is tried again after a growing pause. If that does not help,
    or cannot help, the agent raises AgentError and the engine takes the seat.
    """

    def __init__(
        self,
        call: ModelCall,
        plugin: GamePlugin,
        *,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ):
        self._call = call
        self._game = plugin.name
        self._rules = plugin.rules()
        self._sleep = sleep

    async def act(self, request: TurnRequest) -> Reply:
        messages = build_messages(self._game, self._rules, request)
        return _read(await self._call_model(messages, tool_schemas(request.tools)))

    async def _call_model(self, messages: list[Message], tools: list[dict[str, Any]]) -> ModelReply:
        tries = 0
        while True:
            tries += 1
            try:
                return await self._call(messages, tools)
            except ModelError as error:
                if not error.retryable or tries > MAX_RETRIES:
                    raise AgentError(
                        f"model call failed after {tries} tries ({error.reason})"
                    ) from error
                delay = BACKOFF_SECONDS * 2 ** (tries - 1)
                # Only the kind of failure is logged: never the prompt or a provider message.
                log.warning("Model call failed (%s), next try in %g s", error.reason, delay)
                await self._sleep(delay)


def _read(reply: ModelReply) -> Reply:
    thought = (reply.text or "").strip() or None
    if not reply.tool_calls:
        problem = "Your answer contained no tool call. Call exactly one tool."
        if reply.cut_off:
            problem = (
                "Your answer was cut off at the length limit before it called a tool. "
                "Think in one or two short sentences, then call exactly one tool."
            )
        return Reply(problem=problem, thought=thought)
    call = reply.tool_calls[0]  # one action per request: further calls are ignored
    try:
        arguments = json.loads(call.arguments)
    except (ValueError, RecursionError):
        arguments = None
    if not isinstance(arguments, dict):
        return Reply(
            problem=(
                f"The arguments of your call to '{call.name}' were not a JSON object. "
                "Send them as one JSON object."
            ),
            thought=thought,
        )
    # The thought travels inside the call (see `tool_schemas`); text beside the call is the
    # fallback for a model that wrote its thinking there.
    said = arguments.pop(THOUGHT, None)
    if isinstance(said, str) and said.strip():
        thought = said.strip()
    return Reply(action=Action(tool=call.name, arguments=arguments), thought=thought)
