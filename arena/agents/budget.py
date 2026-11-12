"""Cost caps: every model call of a match is counted, and none may pass a cap."""

import json
import time
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import ROUND_CEILING, Decimal
from typing import Any
from uuid import UUID

from arena.agents.litellm_model import LiteLLMModel
from arena.agents.model import RATE_LIMITED, Message, ModelCall, ModelError, ModelReply
from arena.config import Config, Model, call_options
from arena.db.ledger import Ledger
from arena.engine.types import PlayerId

MICRO = 1_000_000  # money is counted in whole millionths of a euro


class Budget:
    """What one match may spend on model calls.

    A model call wrapped by `meter` is booked in the ledger before it is sent,
    at the most it can cost. If that could take the match or the month past its
    cap, the call is not sent and the match pauses (MatchPaused). After the
    user's decision, set a higher `match_cap` or `month_cap` (in millionths of
    a euro) and run the match again.
    """

    def __init__(
        self,
        ledger: Ledger,
        match_id: UUID,
        config: Config,
        *,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
        clock: Callable[[], float] = time.monotonic,
        match_eur: Decimal | None = None,
    ):
        """`match_eur`: the match's own limit (settings.match_budget_eur). It can only lower
        the config's per-match cap, never raise it."""
        cap = (
            config.limits.match_eur
            if match_eur is None
            else min(match_eur, config.limits.match_eur)
        )
        self.match_cap = int(cap * MICRO)
        self.month_cap = int(config.limits.month_eur * MICRO)
        self._ledger = ledger
        self._match_id = match_id
        self._config = config
        self._now = now
        self._clock = clock

    def model(self, player: PlayerId, model_id: str) -> ModelCall:
        """The metered call of a model from the config. Nothing else builds a real model."""
        model = self._config.models[model_id]
        options = call_options(self._config, model_id)
        real = LiteLLMModel(
            f"{model.provider}/{model.model}",
            max_output_tokens=options.max_output_tokens,
            reasoning_effort=options.reasoning_effort,
            tool_choice=options.tool_choice,
        )
        return self.meter(player, model_id, real)

    def meter(self, player: PlayerId, model_id: str, call: ModelCall) -> ModelCall:
        """Wrap `call` so that its cost is counted at the prices of `model_id`."""
        model = self._config.models[model_id]
        limits = self._config.limits

        async def metered(messages: list[Message], tools: list[dict[str, Any]]) -> ModelReply:
            # No tokenizer makes more tokens than its text has bytes, so the
            # size of the request is an upper bound of its input tokens.
            input_bound = len(json.dumps([messages, tools]))
            if input_bound > limits.max_input_tokens:
                raise ModelError("PromptTooLong", retryable=False)
            call_id = await self._ledger.book(
                self._match_id,
                player,
                model_id,
                # The most it can cost: this model's own output limit, if it has one.
                self._cost(
                    model, input_bound, call_options(self._config, model_id).max_output_tokens
                ),
                match_cap=self.match_cap,
                month_cap=self.month_cap,
                now=self._now(),
            )
            # If the call fails or is cancelled here, the booking stays as it is:
            # the provider may have billed it anyway. Not so a rate limit: a 429 is
            # refused before anything is generated, so it costs nothing.
            sent = self._clock()
            try:
                reply = await call(messages, tools)
            except ModelError as error:
                if error.reason == RATE_LIMITED:
                    latency_ms = round((self._clock() - sent) * 1000)
                    await self._ledger.settle(call_id, 0, 0, 0, latency_ms=latency_ms)
                raise
            latency_ms = round((self._clock() - sent) * 1000)
            if reply.usage is None:
                await self._ledger.timed(call_id, latency_ms)
            else:
                await self._ledger.settle(
                    call_id,
                    reply.usage.input_tokens,
                    reply.usage.output_tokens,
                    self._cost(model, reply.usage.input_tokens, reply.usage.output_tokens),
                    latency_ms=latency_ms,
                    reasoning_tokens=reply.usage.reasoning_tokens,
                )
            return reply

        return metered

    def _cost(self, model: Model, input_tokens: int, output_tokens: int) -> int:
        return cost_micro_eur(self._config, model, input_tokens, output_tokens)


def cost_micro_eur(config: Config, model: Model, input_tokens: float, output_tokens: float) -> int:
    """What a call of `model` with these tokens costs, in millionths of a euro, rounded up."""
    micro_usd = (
        Decimal(input_tokens) * model.input_usd_per_mtok
        + Decimal(output_tokens) * model.output_usd_per_mtok
    )
    micro_eur = micro_usd * config.limits.usd_to_eur
    return int(micro_eur.to_integral_value(rounding=ROUND_CEILING))
