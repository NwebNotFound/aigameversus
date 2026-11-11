"""Runs one match: asks agents, validates their actions and records every event."""

import asyncio
import json
import random
from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Any

import jsonschema
from pydantic import BaseModel

from arena.engine.plugin import GamePlugin, TurnContext
from arena.engine.rng import derive_rng
from arena.engine.types import (
    Action,
    Agent,
    Event,
    EventSource,
    Placement,
    PlayerId,
    ToolSpec,
    TurnMode,
    TurnRequest,
)

MAX_CORRECTIONS = 2  # retries after a rejected action, before the random fallback plays

# Receives new events with the log position of the first one. Called once per turn.
EventSink = Callable[[int, Sequence[Event]], Awaitable[None]]


class PluginError(Exception):
    """A game plugin broke the engine contract."""


class Match[StateT: BaseModel]:
    """One match of one game. Create it, `await run()` once, then read `events` and `state`.

    With a `sink`, the events of each turn are handed over together when the
    turn is complete, so a stored log never ends in the middle of a turn.
    """

    def __init__(
        self,
        plugin: GamePlugin[StateT],
        agents: Mapping[PlayerId, Agent],
        *,
        seed: int,
        settings: Mapping[str, Any] | None = None,
        sink: EventSink | None = None,
    ):
        players = list(agents)
        if not plugin.min_players <= len(players) <= plugin.max_players:
            raise ValueError(
                f"{plugin.id} needs {plugin.min_players} to {plugin.max_players} players, "
                f"got {len(players)}"
            )
        self.plugin = plugin
        self.seed = seed
        self.settings = dict(settings or {})
        self.state = plugin.initial_state(players, self.settings)
        self.events: list[Event] = []
        self._agents = dict(agents)
        self._sink = sink
        self._flushed = 0
        self._game_events = 0
        self._used_streams: set[tuple[str | int, ...]] = set()
        self._ctx = TurnContext(self._stream, self._record_game_event)

    async def run(self) -> list[Placement]:
        plugin = self.plugin
        self._record_engine_event(
            "match_started",
            {
                "game": plugin.id,
                "version": plugin.version,
                "players": list(self._agents),
                "settings": dict(self.settings),
                "seed": self.seed,
            },
            # Spectators only: a player who knows the seed knows every hidden draw.
            visible_to=(),
        )
        plugin.setup(self.state, self._ctx)
        await self._flush()
        while not plugin.is_over(self.state):
            await self._advance()
            await self._flush()
        placements = plugin.results(self.state)
        self._record_engine_event(
            "match_finished", {"placements": [p.model_dump() for p in placements]}
        )
        await self._flush()
        return placements

    async def _flush(self) -> None:
        if self._sink is not None:
            await self._sink(self._flushed, self.events[self._flushed :])
        self._flushed = len(self.events)

    async def _advance(self) -> None:
        plugin = self.plugin
        progress = self._game_events
        active = plugin.active_players(self.state)
        if plugin.turn_mode is TurnMode.SEQUENTIAL and len(active) > 1:
            raise PluginError(f"{plugin.id} is sequential but has {len(active)} active players")
        if active:
            # Everyone decides on the same state. Trails are appended in player
            # order afterwards, so the log does not depend on who answered first.
            decisions = await asyncio.gather(*(self._decide(player) for player in active))
            actions = {}
            for player, (action, trail) in zip(active, decisions, strict=True):
                self.events.extend(trail)
                actions[player] = action
            plugin.apply_actions(self.state, actions, self._ctx)
        if not plugin.is_over(self.state):
            plugin.step(self.state, self._ctx)
        if self._game_events == progress:
            raise PluginError(f"{plugin.id} made no progress: a turn passed without a game event")

    async def _decide(self, player: PlayerId) -> tuple[Action, list[Event]]:
        """Get a legal action from a player, with the events that led to it."""
        plugin = self.plugin
        observation = plugin.get_observation(self.state, player)
        tools = plugin.get_tools(self.state, player)
        trail: list[Event] = []
        error = None
        for _ in range(1 + MAX_CORRECTIONS):
            request = TurnRequest(player=player, observation=observation, tools=tools, error=error)
            action = await self._agents[player].act(request)
            error = self._check(player, action, tools)
            attempt = {"player": player, "tool": action.tool, "arguments": action.arguments}
            if error is None:
                trail.append(_engine_event("action_accepted", attempt, visible_to=(player,)))
                return action, trail
            trail.append(
                _engine_event("action_rejected", attempt | {"error": error}, visible_to=(player,))
            )

        action = plugin.random_action(
            observation, tools, derive_rng(self.seed, "fallback", player, self._game_events)
        )
        error = self._check(player, action, tools)
        if error is not None:
            raise PluginError(f"random_action of {plugin.id} is not legal: {error}")
        trail.append(
            _engine_event(
                "action_fallback",
                {"player": player, "tool": action.tool, "arguments": action.arguments},
                visible_to=(player,),
            )
        )
        return action, trail

    def _check(self, player: PlayerId, action: Action, tools: list[ToolSpec]) -> str | None:
        spec = next((tool for tool in tools if tool.name == action.tool), None)
        if spec is None:
            available = ", ".join(tool.name for tool in tools)
            return f"Tool '{action.tool}' is not available now. Available tools: {available}."
        try:
            jsonschema.validate(action.arguments, spec.parameters)
        except jsonschema.ValidationError as invalid:
            return f"Invalid arguments for '{action.tool}': {invalid.message}."
        return self.plugin.validate(self.state, player, action)

    def _stream(self, *key: str | int) -> random.Random:
        if key in self._used_streams:
            raise PluginError(f"{self.plugin.id} asked for random stream {key} twice")
        self._used_streams.add(key)
        return derive_rng(self.seed, "game", *key)

    def _record_game_event(self, event: Event) -> None:
        # A stored event must come back exactly as it was applied here.
        if json.loads(json.dumps(event.data)) != event.data:
            raise PluginError(
                f"{self.plugin.id} event {event.type!r} has data that JSON would change "
                "(use lists, not tuples, and string keys)"
            )
        self.plugin.apply_event(self.state, event)
        self.events.append(event)
        self._game_events += 1

    def _record_engine_event(
        self, type: str, data: dict[str, Any], *, visible_to: tuple[PlayerId, ...] | None = None
    ) -> None:
        self.events.append(_engine_event(type, data, visible_to=visible_to))


def _engine_event(
    type: str, data: dict[str, Any], *, visible_to: tuple[PlayerId, ...] | None = None
) -> Event:
    return Event(source=EventSource.ENGINE, type=type, data=data, visible_to=visible_to)
