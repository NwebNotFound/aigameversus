"""The random bot: fills a seat without a model, so matches cost nothing."""

import random
from collections.abc import Sequence

from arena.engine.plugin import GamePlugin
from arena.engine.rng import derive_rng
from arena.engine.types import PlayerId, Reply, TurnRequest


class RandomBot:
    """Plays random legal actions, chosen by the game's own `random_action`."""

    def __init__(self, plugin: GamePlugin, rng: random.Random):
        self._plugin = plugin
        self._rng = rng

    async def act(self, request: TurnRequest) -> Reply:
        action = self._plugin.random_action(request.observation, request.tools, self._rng)
        return Reply(action=action)


def random_bots(
    plugin: GamePlugin, players: Sequence[PlayerId], seed: int
) -> dict[PlayerId, RandomBot]:
    """One random bot per seat, each with its own stream derived from the seed."""
    return {player: RandomBot(plugin, derive_rng(seed, "bot", player)) for player in players}
