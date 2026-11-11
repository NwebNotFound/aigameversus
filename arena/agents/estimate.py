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
from arena.config import Config
from arena.engine.match import Match
from arena.engine.plugin import GamePlugin
from arena.engine.types import PlayerId, Reply, TurnRequest

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


class _Measured:
    """Plays a random bot and records the size of the prompt its model would have got."""

    def __init__(self, bot: Any, plugin: GamePlugin, settings: Mapping[str, Any]):
        self._bot, self._plugin, self._settings = bot, plugin, settings
        self._rules = plugin.rules(settings)
        self.sizes: list[int] = []

    async def act(self, request: TurnRequest) -> Reply:
        summary = self._plugin.situation_summary(request.observation, self._settings)
        messages = build_messages(self._plugin.name, self._rules, request, summary)
        self.sizes.append(len(json.dumps([messages, tool_schemas(request.tools)])))
        return await self._bot.act(request)


async def estimate(
    plugin: GamePlugin,
    seats: Mapping[PlayerId, str],
    settings: Mapping[str, Any],
    config: Config,
    output_history: Mapping[str, tuple[int, float]],
) -> dict[PlayerId, SeatEstimate]:
    """The estimated cost of every seat: seat -> model id from config/models.yaml.

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
            priced = _priced(config, model_id, agents[seat].sizes, output_history)
            if seat not in worst or priced.estimate_micro_eur > worst[seat].estimate_micro_eur:
                worst[seat] = priced
    return worst


def _priced(
    config: Config,
    model_id: str,
    sizes: Sequence[int],
    output_history: Mapping[str, tuple[int, float]],
) -> SeatEstimate:
    answers, mean = output_history.get(model_id, (0, 0.0))
    known = answers >= HISTORY_MIN
    output = mean if known else config.limits.max_output_tokens
    input_tokens = sum(sizes) / BYTES_PER_TOKEN * RETRY_SHARE
    output_tokens = len(sizes) * output * RETRY_SHARE
    cost = cost_micro_eur(config, config.models[model_id], input_tokens, output_tokens)
    return SeatEstimate(
        model_id=model_id,
        calls=len(sizes),
        estimate_micro_eur=cost,
        basis="ledger history" if known else "output limit",
    )
