"""A minimal game for engine tests, in one variant per turn mode.

Every round each player adds 1, 2 or 3 to their total, but never the amount
they added last time. The highest total after the last round wins. In the tick
variant players act only on even ticks; odd ticks pass without a decision.
"""

import asyncio
import random
from collections.abc import Mapping, Sequence
from typing import Any

from pydantic import BaseModel

from arena.engine.plugin import GamePlugin, TurnContext
from arena.engine.types import (
    Action,
    Event,
    Placement,
    PlayerId,
    Reply,
    ToolSpec,
    TurnMode,
    TurnRequest,
)

AMOUNTS = (1, 2, 3)

ADD = ToolSpec(
    name="add",
    description="Add an amount to your total.",
    parameters={
        "type": "object",
        "properties": {"amount": {"type": "integer", "minimum": 1, "maximum": 3}},
        "required": ["amount"],
        "additionalProperties": False,
    },
)


class CounterState(BaseModel):
    players: list[PlayerId]
    rounds: int
    clock: int = 0  # closed rounds (ticks in the tick variant)
    amounts: dict[PlayerId, list[int]]
    waiting: list[PlayerId]  # players who have not acted in the open round


class CounterGame(GamePlugin[CounterState]):
    id = "counter"
    name = "Counter"
    version = "1"
    min_players = 2
    max_players = 3

    def initial_state(
        self, players: Sequence[PlayerId], settings: Mapping[str, Any]
    ) -> CounterState:
        return CounterState(
            players=list(players),
            rounds=settings.get("rounds", 2),
            amounts={player: [] for player in players},
            waiting=list(players),
        )

    def setup(self, state: CounterState, ctx: TurnContext) -> None:
        pass

    def _is_quiet_tick(self, state: CounterState) -> bool:
        return self.turn_mode is TurnMode.TICK and state.clock % 2 == 1

    def active_players(self, state: CounterState) -> list[PlayerId]:
        if self._is_quiet_tick(state):
            return []
        if self.turn_mode is TurnMode.SEQUENTIAL:
            return state.waiting[:1]
        return list(state.waiting)

    def get_observation(self, state: CounterState, player: PlayerId) -> dict[str, Any]:
        return {"amounts": {p: list(a) for p, a in state.amounts.items()}, "you": player}

    def get_tools(self, state: CounterState, player: PlayerId) -> list[ToolSpec]:
        return [ADD]

    def validate(self, state: CounterState, player: PlayerId, action: Action) -> str | None:
        if state.amounts[player][-1:] == [action.arguments["amount"]]:
            return "You may not add the same amount twice in a row."
        return None

    def apply_actions(
        self, state: CounterState, actions: Mapping[PlayerId, Action], ctx: TurnContext
    ) -> None:
        for player, action in actions.items():
            ctx.emit("added", {"player": player, "amount": action.arguments["amount"]})

    def step(self, state: CounterState, ctx: TurnContext) -> None:
        if not state.waiting or self._is_quiet_tick(state):
            ctx.emit("round_closed", {"clock": state.clock + 1})

    def apply_event(self, state: CounterState, event: Event) -> None:
        match event.type:
            case "added":
                state.amounts[event.data["player"]].append(event.data["amount"])
                state.waiting.remove(event.data["player"])
            case "round_closed":
                state.clock = event.data["clock"]
                state.waiting = list(state.players)

    def is_over(self, state: CounterState) -> bool:
        return state.clock >= state.rounds

    def results(self, state: CounterState) -> list[Placement]:
        totals = {player: sum(amounts) for player, amounts in state.amounts.items()}
        return [
            Placement(player=player, rank=1 + sum(other > total for other in totals.values()))
            for player, total in totals.items()
        ]

    def random_action(
        self, observation: Mapping[str, Any], tools: Sequence[ToolSpec], rng: random.Random
    ) -> Action:
        last = observation["amounts"][observation["you"]][-1:]
        return add(rng.choice([amount for amount in AMOUNTS if [amount] != last]))


class SequentialCounter(CounterGame):
    turn_mode = TurnMode.SEQUENTIAL


class SimultaneousCounter(CounterGame):
    turn_mode = TurnMode.SIMULTANEOUS


class TickCounter(CounterGame):
    turn_mode = TurnMode.TICK


HANGS = object()  # script step of `Scripted`: the agent never answers


class Scripted:
    """An agent that follows a script and remembers what it was asked.

    A step is an Action or a Reply to answer with, an exception to raise, or HANGS.
    """

    def __init__(self, *steps: Action | Reply | Exception | object):
        self._steps = list(steps)
        self.requests: list[TurnRequest] = []

    async def act(self, request: TurnRequest) -> Reply:
        self.requests.append(request)
        step = self._steps.pop(0)
        if step is HANGS:
            await asyncio.Event().wait()
        if isinstance(step, Exception):
            raise step
        return Reply(action=step) if isinstance(step, Action) else step


def add(amount: Any) -> Action:
    return Action(tool="add", arguments={"amount": amount})
