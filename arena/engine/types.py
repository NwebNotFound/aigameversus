"""Value types shared by the engine, game plugins and agents."""

from enum import StrEnum
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field

PlayerId = str


class TurnMode(StrEnum):
    """How many players a game asks for an action at the same time."""

    SEQUENTIAL = "sequential"  # at most one player at a time
    SIMULTANEOUS = "simultaneous"  # several players decide on the same state
    TICK = "tick"  # the game also advances on steps where nobody decides


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True)


class ToolSpec(_Frozen):
    """An action a player may take right now, described for function calling."""

    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema of the arguments object


class Action(_Frozen):
    """A tool call proposed by a player. It has no effect until the server accepts it."""

    tool: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class EventSource(StrEnum):
    ENGINE = "engine"  # bookkeeping: match start and end, accepted and rejected actions
    GAME = "game"  # emitted by the plugin; the game state is exactly the sum of these


class Event(_Frozen):
    """One entry of a match log.

    `visible_to` is None for public events. Otherwise only the listed players
    may see the event; an empty tuple means spectators only.
    """

    source: EventSource
    type: str
    data: dict[str, Any] = Field(default_factory=dict)
    visible_to: tuple[PlayerId, ...] | None = None

    def is_visible_to(self, player: PlayerId) -> bool:
        return self.visible_to is None or player in self.visible_to


class Placement(_Frozen):
    """Final standing of one player.

    Rank 1 is the winner. Tied players share a rank and the next rank is
    skipped: 1, 1, 3.
    """

    player: PlayerId
    rank: int


class TurnRequest(_Frozen):
    """What an agent gets when it is asked to act."""

    player: PlayerId
    observation: dict[str, Any]
    tools: tuple[ToolSpec, ...]
    error: str | None = None  # why the previous attempt of this turn was rejected


class Agent(Protocol):
    """Anything that can take a seat: a random bot, a mock LLM or a real model."""

    async def act(self, request: TurnRequest) -> Action: ...
