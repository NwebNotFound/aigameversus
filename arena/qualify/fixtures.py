"""Qualification fixtures: real turn requests, captured from seeded random-bot matches.

A fixture is one turn of one seat in a bot match with a fixed seed: the player's own
observation, its tools and the events it has seen, exactly as the engine would ask a model
(research/QUALIFY.md: player observations, never spectator state). The game state of that
moment is kept too, so the model's answer is judged by the game's own validator.

Fixtures are rebuilt on every run from (game, players, settings, seed, case), so they cannot
touch a running match or its randomness, and a change of the game changes their hash.
"""

from __future__ import annotations

import asyncio
import copy
import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from arena.agents.random_bot import random_bots
from arena.engine.match import Match
from arena.engine.plugin import GamePlugin
from arena.engine.types import Reply, ToolSpec, TurnRequest

SEARCH_SEEDS = 40  # seeds tried in order until a turn fits the case
MAX_TURNS = 400  # of one search match: a fixture never waits for a whole long game


@dataclass(frozen=True)
class Fixture:
    case: str
    seed: int
    request: TurnRequest  # what the model is sent: the offered tools only
    state: Any  # the game state of that turn, for the game's validator; never sent
    sha256: str  # of the request, canonical JSON


class _Found(Exception):
    def __init__(self, state: Any, request: TurnRequest):
        self.state, self.request = state, request


class _Probe:
    """The probed seat: plays like a random bot, and stops the match at the first fitting turn."""

    def __init__(self, inner, fits: Callable[[TurnRequest], bool], longest: bool):
        self._inner = inner
        self._fits = fits
        self._longest = longest
        self.match: Match | None = None
        self.best: tuple[int, Any, TurnRequest] | None = None

    async def act(self, request: TurnRequest) -> Reply:
        if request.error is None and self._fits(request):
            assert self.match is not None
            state = copy.deepcopy(self.match.state)
            if not self._longest:
                raise _Found(state, request)
            size = len(canonical(request))
            if self.best is None or size > self.best[0]:
                self.best = (size, state, request)
        return await self._inner.act(request)


def canonical(request: TurnRequest) -> str:
    return json.dumps(request.model_dump(mode="json"), sort_keys=True, ensure_ascii=False)


def capture(
    plugin: GamePlugin,
    players: list[str],
    settings: dict[str, Any],
    player: str,
    fits: Callable[[TurnRequest], bool],
    offer: Callable[[list[ToolSpec]], list[ToolSpec]],
    *,
    case: str,
    longest: bool = False,
) -> Fixture | None:
    """The first turn of `player` that fits (or, with `longest`, the turn with the most
    history), over seeds 1, 2, 3, ...; None if no seed of the search has one.

    `offer` narrows the tools the model is offered (QUALIFY.md: constrain where needed so
    success can be checked); an offered tool is always one the engine offered.
    """
    best: tuple[int, int, Any, TurnRequest] | None = None  # size, seed, state, request
    for seed in range(1, SEARCH_SEEDS + 1):
        agents = random_bots(plugin, players, seed)
        probe = _Probe(agents[player], fits, longest)
        agents[player] = probe
        match = Match(plugin, agents, seed=seed, settings=settings, max_turns=MAX_TURNS)
        probe.match = match
        try:
            asyncio.run(_play(match))
        except _Found as found:
            return _fixture(case, seed, found.state, found.request, offer)
        if probe.best is not None and (best is None or probe.best[0] > best[0]):
            best = (probe.best[0], seed, probe.best[1], probe.best[2])
    if best is None:
        return None
    _, seed, state, request = best
    return _fixture(case, seed, state, request, offer)


async def _play(match: Match) -> None:
    try:
        await match.run()
    except _Found:
        raise
    except Exception:  # noqa: BLE001 - a search match that ends badly simply has no fixture
        return


def _fixture(case, seed, state, request: TurnRequest, offer) -> Fixture:
    offered = offer(list(request.tools))
    names = {tool.name for tool in request.tools}
    assert offered and all(tool.name in names for tool in offered), "offer only engine tools"
    narrowed = request.model_copy(update={"tools": tuple(offered)})
    digest = hashlib.sha256(canonical(narrowed).encode()).hexdigest()
    return Fixture(case=case, seed=seed, request=narrowed, state=state, sha256=digest)
