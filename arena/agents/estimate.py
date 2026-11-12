"""What a match with models would cost, estimated without calling any model.

Random bots play the match a few times; on every turn the prompt each seat's
model would get is built and measured, as the agent runner builds it. The
cost of a seat is its prompts as input tokens plus an answer per prompt,
priced like the budget prices a call.
"""

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from arena.agents.budget import cost_micro_eur
from arena.agents.prompt import build_messages, tool_schemas
from arena.agents.random_bot import random_bots
from arena.agents.runner import escalation, output_limits
from arena.config import Config, call_options
from arena.engine.match import Match
from arena.engine.plugin import GamePlugin
from arena.engine.types import PlayerId, Reply, TurnRequest, adaptive_output_of

SEEDS = (1, 2, 3)  # the estimate is the most expensive of these matches, per seat
BYTES_PER_TOKEN = 3.5  # JSON-heavy English; a low guess makes the estimate high
RETRY_SHARE = 1.3  # corrections and retries on top of one answer per turn
HISTORY_MIN = 10  # answers of a model in the ledger before its own mean output is used


Basis = Literal["ledger history", "output limit"]


@dataclass(frozen=True)
class SeatEstimate:
    model_id: str
    calls: int  # prompts in the most expensive of the matches played
    estimate_micro_eur: int
    basis: Basis  # how its answers were counted: its mean in the ledger, or the output limit
    # Every answer at the most it may cost: its output limit, and with adaptive_output every
    # raised limit up to the ceiling, each call with its whole prompt (D-143).
    worst_case_micro_eur: int


class _Measured:
    """Plays a random bot and records the size of the prompt its model would have got."""

    def __init__(self, bot: Any, plugin: GamePlugin, settings: Mapping[str, Any]):
        self._bot, self._plugin, self._settings = bot, plugin, settings
        self._rules = plugin.rules(settings)
        self.sizes: list[int] = []

    async def act(self, request: TurnRequest) -> Reply:
        summary = self._plugin.situation_summary(request.observation, self._settings)
        messages = build_messages(
            self._plugin.name,
            self._rules,
            request,
            summary,
            history_limit=self._plugin.history_limit(self._settings),
        )
        self.sizes.append(len(json.dumps([messages, tool_schemas(request.tools)])))
        return await self._bot.act(request)


async def estimate(
    plugin: GamePlugin,
    seats: Mapping[PlayerId, str | None],
    settings: Mapping[str, Any],
    config: Config,
    output_history: Mapping[str, tuple[int, float]],
) -> dict[PlayerId, SeatEstimate]:
    """The estimated cost of every model seat: seat -> model id, None for a bot seat.

    `output_history` is what the ledger knows: model id -> (answers, mean output tokens).
    A model with fewer than HISTORY_MIN answers is counted at the output limit, the most
    an answer may cost. Raises ValueError for a player count or settings the game refuses.
    """
    worst: dict[PlayerId, SeatEstimate] = {}
    for seed in SEEDS:
        bots = random_bots(plugin, list(seats), seed)
        agents = {seat: _Measured(bots[seat], plugin, settings) for seat in seats}
        await Match(plugin, agents, seed=seed, settings=settings).run()
        for seat, model_id in seats.items():
            if model_id is None:  # a bot seat plays, so the others' prompts are real, but is free
                continue
            priced = _priced(
                config, model_id, agents[seat].sizes, output_history, adaptive_output_of(settings)
            )
            if seat not in worst or priced.estimate_micro_eur > worst[seat].estimate_micro_eur:
                worst[seat] = priced
    return worst


def _priced(
    config: Config,
    model_id: str,
    sizes: Sequence[int],
    output_history: Mapping[str, tuple[int, float]],
    adaptive: bool = False,
) -> SeatEstimate:
    answers, mean = output_history.get(model_id, (0, 0.0))
    known = answers >= HISTORY_MIN
    # Without history, the most an answer may cost: the model's own output limit, as the
    # budget books it (`call_options`), not the global one.
    output = mean if known else call_options(config, model_id).max_output_tokens
    input_tokens = sum(sizes) / BYTES_PER_TOKEN * RETRY_SHARE
    output_tokens = len(sizes) * output * RETRY_SHARE
    model = config.models[model_id]
    cost = cost_micro_eur(config, model, input_tokens, output_tokens)
    limits = output_limits(config, model_id)
    chain = escalation(limits) if adaptive else [limits.start]
    worst = cost_micro_eur(
        config,
        model,
        input_tokens * len(chain),
        len(sizes) * sum(chain) * RETRY_SHARE,
    )
    return SeatEstimate(
        model_id=model_id,
        calls=len(sizes),
        estimate_micro_eur=cost,
        basis="ledger history" if known else "output limit",
        worst_case_micro_eur=max(cost, worst),
    )
