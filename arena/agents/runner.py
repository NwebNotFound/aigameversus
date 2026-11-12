"""The agent runner: a seat played by a language model."""

import asyncio
import logging
import random
from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Any

from arena.agents.arguments import as_sent, read_arguments
from arena.agents.model import RATE_LIMITED, Message, ModelCall, ModelError, ModelReply
from arena.agents.prompt import HEADLINE, HEADLINE_CHARS, THOUGHT, build_messages, tool_schemas
from arena.engine.plugin import GamePlugin
from arena.engine.types import (
    Action,
    AgentError,
    AnswerStats,
    Reply,
    ToolSpec,
    TurnRequest,
    headline_of,
    repair_of,
)

log = logging.getLogger(__name__)

MAX_RETRIES = 3  # further tries after a failed model call
MALFORMED_LIMIT = 3  # garbled calls in a match before the tools come without `thought`
RAW_CHARS = 2000  # of a garbled call, kept for spectators and research
BACKOFF_SECONDS = 1.0  # pause before the first retry; doubles with every retry
RATE_LIMIT_BACKOFF_SECONDS = 3.0  # it needs longer: 3, 6, 12 s (and the jitter)
RATE_LIMIT_RETRIES_PER_MATCH = 12  # after these, a rate limit is no longer waited out
JITTER = 0.5  # each pause is up to this share longer, so seats do not retry in step


class ModelAgent:
    """Plays one seat by asking a model.

    Each turn it builds the prompt, calls the model and reads the answer: text
    is the private thought, the first tool call is the action. It does not
    judge the action; the engine does.

    A failed call is tried again after a growing pause. If that does not help,
    or cannot help, the agent raises AgentError and the engine takes the seat.
    A rate limit gets longer pauses, and only RATE_LIMIT_RETRIES_PER_MATCH of
    them in a match: a model that is throttled all the time loses its seat
    instead of stretching every turn to its time limit.
    """

    def __init__(
        self,
        call: ModelCall,
        plugin: GamePlugin,
        *,
        settings: Mapping[str, Any] | None = None,
        memory: str | None = None,
        personality: str | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        jitter: Callable[[], float] = random.random,
    ):
        """`memory`: what this player remembers of the opponents (`arena/memory/block.py`).

        `personality`: the character this player plays (`prompt.personality_text`).
        """
        self._call = call
        self._memory = memory
        self._personality = personality
        self._plugin = plugin
        self._settings = settings
        self._rules = plugin.rules(settings)
        self._sleep = sleep
        self._jitter = jitter  # 0 to 1; the pauses only, never the game's randomness
        self._rate_limit_retries = RATE_LIMIT_RETRIES_PER_MATCH
        self._malformed = 0  # answers of this match whose call was garbled
        self._repair = repair_of(settings or {}) != "off"
        self._headline = headline_of(settings or {})

    async def act(self, request: TurnRequest) -> Reply:
        summary = self._plugin.situation_summary(request.observation, self._settings)
        messages = build_messages(
            self._plugin.name, self._rules, request, summary, self._memory, self._personality
        )
        simple = self._repair and self._malformed >= MALFORMED_LIMIT
        schemas = tool_schemas(request.tools, with_thought=not simple, headline=self._headline)
        answer, tries = await self._call_model(messages, schemas)
        reply, repairs, raw = _read(
            answer, request.tools, repair=self._repair, headline=self._headline
        )
        if repairs or raw is not None:
            self._malformed += 1
        usage = answer.usage
        stats = AnswerStats(
            tokens_in=usage.input_tokens if usage else None,
            tokens_out=usage.output_tokens if usage else None,
            reasoning_tokens=usage.reasoning_tokens if usage else None,
            retries=tries - 1,
            repairs=tuple(repairs),
            raw_arguments=raw,
            simple_schema=simple,
        )
        return reply.model_copy(update={"stats": stats})

    async def _call_model(
        self, messages: list[Message], tools: list[dict[str, Any]]
    ) -> tuple[ModelReply, int]:
        """The model's answer and how many calls it took."""
        tries = 0
        while True:
            tries += 1
            try:
                return await self._call(messages, tools), tries
            except ModelError as error:
                rate_limited = error.reason == RATE_LIMITED
                used_up = rate_limited and self._rate_limit_retries == 0
                if not error.retryable or tries > MAX_RETRIES or used_up:
                    why = "; the rate-limit retries of this match are used up" if used_up else ""
                    raise AgentError(
                        f"model call failed after {tries} tries ({error.reason}){why}"
                    ) from error
                if rate_limited:
                    self._rate_limit_retries -= 1
                base = RATE_LIMIT_BACKOFF_SECONDS if rate_limited else BACKOFF_SECONDS
                delay = base * 2 ** (tries - 1) * (1 + JITTER * self._jitter())
                # Only the kind of failure is logged: never the prompt or a provider message.
                log.warning("Model call failed (%s), next try in %g s", error.reason, delay)
                await self._sleep(delay)


def _read(
    reply: ModelReply, tools: Sequence[ToolSpec], *, repair: bool, headline: bool = False
) -> tuple[Reply, list[str], str | None]:
    """The reply, the repairs made to its call, and the raw call if it was garbled.

    Without `repair` (answer_repair "off") the arguments are read as sent: anything but
    one JSON object is a problem, and every key goes to the engine.
    """
    thought = (reply.text or "").strip() or None
    if not reply.tool_calls:
        problem = "Your answer contained no tool call. Call exactly one tool."
        if reply.cut_off:
            problem = (
                "Your answer was cut off at the length limit before it called a tool. "
                "Think in one or two short sentences, then call exactly one tool."
            )
        return Reply(problem=problem, thought=thought), [], None
    call = reply.tool_calls[0]  # one action per request: further calls are ignored
    spec = next((tool for tool in tools if tool.name == call.name), None)
    if not repair:
        arguments, repairs, raw = as_sent(call.arguments), [], None
    else:
        arguments, repairs = read_arguments(call.arguments, spec, THOUGHT)
        raw = str(call.arguments)[:RAW_CHARS] if repairs or arguments is None else None
    if arguments is None:
        problem = (
            f"The arguments of your call to '{call.name}' were not a JSON object. "
            "Send them as one JSON object."
        )
        return Reply(problem=problem, thought=thought), repairs, raw
    # The thought travels inside the call (see `tool_schemas`); text beside the call is the
    # fallback for a model that wrote its thinking there.
    said = arguments.pop(THOUGHT, None)
    if isinstance(said, str) and said.strip():
        thought = said.strip()
    line = arguments.pop(HEADLINE, None) if headline else None  # only with thought_headline
    short = line.strip()[:HEADLINE_CHARS] if isinstance(line, str) and line.strip() else None
    action = Action(tool=call.name, arguments=arguments)
    return Reply(action=action, thought=thought, headline=short), repairs, raw
