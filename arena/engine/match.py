"""Runs one match: asks agents, validates their actions and records every event."""

import asyncio
import json
import math
import random
import re
from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Any

import jsonschema
from pydantic import BaseModel

from arena.engine.plugin import GamePlugin, TurnContext
from arena.engine.rng import derive_rng
from arena.engine.types import (
    ANSWER_REPAIR,
    ANSWER_REPAIR_VERSIONS,
    MATCH_BUDGET,
    MESSAGE,
    THOUGHT_HEADLINE,
    Action,
    Agent,
    AgentError,
    AnswerStats,
    Event,
    EventSource,
    MatchPaused,
    Placement,
    PlayerId,
    Reply,
    ToolSpec,
    TurnMode,
    TurnRequest,
    game_settings,
    headline_of,
    repair_of,
)

MAX_CORRECTIONS = 2  # retries after a rejected action, before the random fallback plays
DEFAULT_TURN_TIMEOUT = 60.0  # seconds a player has for one turn, corrections included

# Postgres cannot store these in JSON text: NUL and halves of a surrogate pair.
_UNSTORABLE_CHARACTERS = re.compile(r"[\x00\ud800-\udfff]")

# Receives new events with the log position of the first one. Called once per turn.
EventSink = Callable[[int, Sequence[Event]], Awaitable[None]]


class PluginError(Exception):
    """A game plugin broke the engine contract."""


class Match[StateT: BaseModel]:
    """One match of one game. Create it, `await run()`, then read `events` and `state`.

    With a `sink`, the events of each turn are handed over together when the
    turn is complete, so a stored log never ends in the middle of a turn.

    `turn_timeout` is the time in seconds a player has for one turn, with all
    corrections. When it runs out, a random legal action is played instead.

    `max_turns` is the number of turns after which a match that is still not
    over is stopped as a plugin bug. The default is the game's own `max_turns`.
    """

    def __init__(
        self,
        plugin: GamePlugin[StateT],
        agents: Mapping[PlayerId, Agent],
        *,
        seed: int,
        settings: Mapping[str, Any] | None = None,
        sink: EventSink | None = None,
        turn_timeout: float = DEFAULT_TURN_TIMEOUT,
        max_turns: int | None = None,
        clock: Callable[[], float] | None = None,
        personalities: Mapping[PlayerId, str] | None = None,
    ):
        """`clock` (seconds, e.g. time.monotonic) times every move into its `decision` event.

        Without it the time stays out of the log, so a match is the same each time it is
        played with the same seed and answers. `personalities` (seat -> personality id) is
        recorded in `match_started` when a seat has one.
        """
        players = list(agents)
        if not plugin.min_players <= len(players) <= plugin.max_players:
            raise ValueError(
                f"{plugin.id} needs {plugin.min_players} to {plugin.max_players} players, "
                f"got {len(players)}"
            )
        self.plugin = plugin
        self.seed = seed
        self.settings = dict(settings or {})
        repair = repair_of(self.settings)
        if repair not in ANSWER_REPAIR_VERSIONS:
            raise ValueError(
                f"Unknown {ANSWER_REPAIR} {repair!r}; choose one of {list(ANSWER_REPAIR_VERSIONS)}"
            )
        if not isinstance(self.settings.get(THOUGHT_HEADLINE, False), bool):
            raise ValueError(f"{THOUGHT_HEADLINE} is true or false")
        budget = self.settings.get(MATCH_BUDGET)
        if budget is not None and (
            isinstance(budget, bool) or not isinstance(budget, int | float) or not budget > 0
        ):
            raise ValueError(f"{MATCH_BUDGET} must be a number of euros above 0, not {budget!r}")
        self.state = plugin.initial_state(players, game_settings(self.settings))
        self.events: list[Event] = []
        self._agents = dict(agents)
        self._sink = sink
        self._turn_timeout = turn_timeout
        self._clock = clock
        self._personalities = dict(personalities or {})
        self._max_turns = plugin.max_turns if max_turns is None else max_turns
        self._turns = 0  # completed turns
        self._failed: set[PlayerId] = set()  # seats whose agent gave up for good
        self._paused = False
        self._flushed = 0
        self._game_events = 0
        self._used_streams: set[tuple[str | int, ...]] = set()
        self._ctx = TurnContext(self._stream, self._record_game_event)

    async def run(self) -> list[Placement]:
        """Play the match to its end and return the final standings.

        Raises MatchPaused when an agent cannot go on without the user. The log
        then ends with `match_paused`, and the turn that was being played is
        not in it. Calling `run()` again continues with that turn.
        """
        plugin = self.plugin
        if self._paused:
            self._paused = False
            self._record_engine_event("match_resumed", {}, visible_to=())
        elif self.events:
            raise RuntimeError("This match has already been played")
        else:
            self._record_engine_event(
                "match_started",
                {
                    "game": plugin.id,
                    "version": plugin.version,
                    "players": list(self._agents),
                    "settings": dict(self.settings),
                    "prompt_version": plugin.prompt_version(self.settings),
                    ANSWER_REPAIR: repair_of(self.settings),
                    THOUGHT_HEADLINE: headline_of(self.settings),
                    "seed": self.seed,
                    # Only with a personality: a match without one logs what it always did.
                    **({"personalities": self._personalities} if self._personalities else {}),
                },
                # Spectators only: a player who knows the seed knows every hidden draw.
                visible_to=(),
            )
            plugin.setup(self.state, self._ctx)
            await self._flush()
        try:
            while not plugin.is_over(self.state):
                if self._turns >= self._max_turns:
                    # A game that never ends would play, store and bill forever.
                    self._record_engine_event(
                        "turn_limit_reached", {"max_turns": self._max_turns}, visible_to=()
                    )
                    await self._flush()
                    raise PluginError(
                        f"{plugin.id} is not over after {self._max_turns} turns (max_turns)"
                    )
                await self._advance()
                self._turns += 1
                await self._flush()
        except MatchPaused as pause:
            self._paused = True
            self._record_engine_event(
                "match_paused", {"reason": pause.reason, **pause.data}, visible_to=()
            )
            await self._flush()
            raise
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
            decisions = await self._decide_all(active)
            actions = {}
            for player, (action, trail) in zip(active, decisions, strict=True):
                self.events.extend(trail)
                actions[player] = action
            plugin.apply_actions(self.state, actions, self._ctx)
        if not plugin.is_over(self.state):
            plugin.step(self.state, self._ctx)
        if self._game_events == progress:
            raise PluginError(f"{plugin.id} made no progress: a turn passed without a game event")

    async def _decide_all(self, players: list[PlayerId]) -> list[tuple[Action, list[Event]]]:
        """Let the players decide side by side. All of them succeed, or the turn did not happen."""
        failed_before = set(self._failed)
        deciding = [asyncio.ensure_future(self._decide(player)) for player in players]
        try:
            return await asyncio.gather(*deciding)
        except BaseException:
            # One player stopped the turn, with a pause or a plugin bug. Nobody
            # keeps a model busy for a turn that is dropped, and a seat that
            # failed in it is asked again when the turn is played.
            for decision in deciding:
                decision.cancel()
            await asyncio.gather(*deciding, return_exceptions=True)
            self._failed = failed_before
            raise

    async def _decide(self, player: PlayerId) -> tuple[Action, list[Event]]:
        """Get a legal action for a player, with the events that led to it.

        The agent's own action if it gives a legal one in time. Otherwise a
        random legal action, and the log says why.
        """
        plugin = self.plugin
        observation = plugin.get_observation(self.state, player)
        tools = plugin.get_tools(self.state, player)
        trail: list[Event] = []
        answers: list[AnswerStats | None] = []
        started = self._clock() if self._clock else None
        reason = "agent_failed"
        if player not in self._failed:
            try:
                async with asyncio.timeout(self._turn_timeout):
                    action = await self._ask(player, observation, tools, trail, answers)
                if action is not None:
                    if any(stats is not None for stats in answers):  # a model, not a bot
                        trail.append(self._decision(player, started, answers, None))
                    return action, trail
                reason = "rejected"
            except TimeoutError:
                reason = "timeout"
            except AgentError as error:
                self._failed.add(player)
                trail.append(
                    _engine_event(
                        "agent_failed", {"player": player, "error": str(error)}, visible_to=()
                    )
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
                {
                    "player": player,
                    "tool": action.tool,
                    "arguments": action.arguments,
                    "reason": reason,
                },
                visible_to=(player,),
            )
        )
        trail.append(self._decision(player, started, answers, reason))
        return action, trail

    def _decision(
        self,
        player: PlayerId,
        started: float | None,
        answers: list[AnswerStats | None],
        fallback: str | None,
    ) -> Event:
        """What a move took: time, tokens, calls tried again, and the fallback if one played.

        Spectators only. Logged for every move that ended in a fallback and for every
        move of an agent that reports stats (a model); a bot's move has none. A token
        count is null when no answer of the move reported it.
        """
        reported = [stats for stats in answers if stats is not None]

        def total(field: str) -> int | None:
            counts = [getattr(stats, field) for stats in reported]
            known = [count for count in counts if count is not None]
            return sum(known) if known else None

        latency = None if started is None else round((self._clock() - started) * 1000)
        return _engine_event(
            "decision",
            {
                "player": player,
                "answers": len(answers),
                "latency_ms": latency,
                "tokens_in": total("tokens_in"),
                "tokens_out": total("tokens_out"),
                "reasoning_tokens": total("reasoning_tokens"),
                "retries": sum(stats.retries for stats in reported),
                # Kept apart: a throttled provider or a too small output limit is not a
                # model that cannot call tools.
                "rate_limits": sum(stats.rate_limits for stats in reported),
                "cutoffs": sum(1 for stats in reported if stats.cut_off),
                "fallback": fallback,
                # A repaired move is a valid move but not a clean one: research counts both.
                "repairs": sorted({repair for stats in reported for repair in stats.repairs}),
                "raw_arguments": [s.raw_arguments for s in reported if s.raw_arguments],
                "simple_schema": any(stats.simple_schema for stats in reported),
            },
            visible_to=(),
        )

    async def _ask(
        self,
        player: PlayerId,
        observation: dict[str, Any],
        tools: list[ToolSpec],
        trail: list[Event],
        answers: list[AnswerStats | None],
    ) -> Action | None:
        """Ask the agent until an answer passes every check. None if the last correction failed."""
        error = None
        for _ in range(1 + MAX_CORRECTIONS):
            request = TurnRequest(
                player=player,
                observation=observation,
                tools=tools,
                events=[e for e in (*self.events, *trail) if e.is_visible_to(player)],
                error=error,
            )
            reply = await self._agents[player].act(request)
            reply = Reply.model_validate(_storable(reply.model_dump()))
            answers.append(reply.stats)
            if reply.thought or reply.headline:
                # Spectators only: no player gets a thought, not even its author.
                thought = {"player": player, "text": reply.thought or ""}
                if reply.headline:
                    thought["headline"] = reply.headline
                trail.append(_engine_event("thought", thought, visible_to=()))
            action = reply.action
            error = reply.problem if action is None else self._check(player, action, tools)
            attempt = {
                "player": player,
                "tool": action.tool if action else None,
                "arguments": action.arguments if action else None,
            }
            if error is None:
                trail.append(_engine_event("action_accepted", attempt, visible_to=(player,)))
                return action
            trail.append(
                _engine_event("action_rejected", attempt | {"error": error}, visible_to=(player,))
            )
        return None

    def _check(self, player: PlayerId, action: Action, tools: list[ToolSpec]) -> str | None:
        spec = next((tool for tool in tools if tool.name == action.tool), None)
        if spec is None:
            available = ", ".join(tool.name for tool in tools)
            return f"Tool '{action.tool}' is not available now. Available tools: {available}."
        try:
            jsonschema.validate(action.arguments, spec.parameters)
        except jsonschema.ValidationError as invalid:
            error = f"Invalid arguments for '{action.tool}': {invalid.message}."
            # With answer_repair on, the correction also names the tool's fields.
            return error if repair_of(self.settings) == "off" else f"{error} {_fields(spec)}"
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
        if event.type == MESSAGE and not (
            set(event.data) == {"player", "text"}
            and all(isinstance(value, str) for value in event.data.values())
        ):
            raise PluginError(
                f"{self.plugin.id} emitted a message event whose data is not "
                "{'player': <id>, 'text': <string>}"
            )
        self.plugin.apply_event(self.state, event)
        self.events.append(event)
        self._game_events += 1

    def _record_engine_event(
        self, type: str, data: dict[str, Any], *, visible_to: tuple[PlayerId, ...] | None = None
    ) -> None:
        self.events.append(_engine_event(type, data, visible_to=visible_to))


def _storable(value: Any) -> Any:
    """`value` without anything the event store would refuse.

    Whatever a model writes ends up in the log, and one odd character must not
    stop a match: unstorable characters are dropped, NaN and infinity become
    null, tuples become lists.
    """
    if isinstance(value, str):
        return _UNSTORABLE_CHARACTERS.sub("", value)
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {_storable(key): _storable(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_storable(item) for item in value]
    return value


def _fields(spec: ToolSpec) -> str:
    """What a call of this tool may hold, for a correction."""
    properties = spec.parameters.get("properties") or {}
    if not properties:
        return f"'{spec.name}' takes no arguments: send {{}} (and your thought)."
    required = spec.parameters.get("required") or []
    fields = ", ".join(
        f"{name} ({schema.get('type', 'value')}{', required' if name in required else ''})"
        for name, schema in properties.items()
    )
    return f"'{spec.name}' takes only: {fields}."


def _engine_event(
    type: str, data: dict[str, Any], *, visible_to: tuple[PlayerId, ...] | None = None
) -> Event:
    return Event(source=EventSource.ENGINE, type=type, data=data, visible_to=visible_to)
