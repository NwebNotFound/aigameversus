"""Value types shared by the engine, game plugins and agents."""

from collections.abc import Mapping
from enum import StrEnum
from typing import Any, Protocol, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

PlayerId = str

# Type of the game event that carries text a player wrote. Its data is exactly
# {"player": <author>, "text": <their words>}. Prompts show such text as that
# player's words, never as instructions.
MESSAGE = "message"


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
    events: tuple[Event, ...]  # everything this player has seen so far, oldest first
    error: str | None = None  # why the previous attempt of this turn was rejected


# A match setting of the engine, not of the game: how kindly a model's garbled tool call
# is read ("off": as sent; "v1": arena/agents/arguments.py). Games never see it.
ANSWER_REPAIR = "answer_repair"
ANSWER_REPAIR_VERSIONS = ("off", "v1")
# Whether every tool call also asks for a `headline`: the thought in a line, for viewers.
# Not a prompt version: it is the same prompt for every game, turned on or off.
THOUGHT_HEADLINE = "thought_headline"
ENGINE_SETTINGS = (ANSWER_REPAIR, THOUGHT_HEADLINE)


def repair_of(settings: Mapping[str, Any]) -> str:
    """The answer_repair of a match: its setting, else "off" (the call as sent)."""
    return settings.get(ANSWER_REPAIR, "off")


def headline_of(settings: Mapping[str, Any]) -> bool:
    """Whether a match asks its models for a headline with every thought (default no)."""
    return settings.get(THOUGHT_HEADLINE, False) is True


def game_settings(settings: Mapping[str, Any]) -> dict[str, Any]:
    """The settings of a match without the engine's own: what the game is given."""
    return {key: value for key, value in settings.items() if key not in ENGINE_SETTINGS}


class AnswerStats(_Frozen):
    """What one answer of a model took, as far as its provider said."""

    tokens_in: int | None = None
    tokens_out: int | None = None
    reasoning_tokens: int | None = None
    retries: int = 0  # failed calls tried again before this answer
    rate_limits: int = 0  # of those, the ones the provider refused as too many requests
    cut_off: bool = False  # the answer ran into the output limit
    repairs: tuple[str, ...] = ()  # how a garbled call was read (arena/agents/arguments.py)
    raw_arguments: str | None = None  # the call as sent, when it was repaired or unreadable
    simple_schema: bool = False  # the model was offered its tools without `thought`


class Reply(_Frozen):
    """What an agent answers: one action, or the reason why there is none.

    `thought` is the agent's private reasoning. The engine logs it for
    spectators only; no player ever gets it, not even its author. `stats` is
    what the answer took (a model agent's; None for a bot), logged for
    spectators in the move's `decision` event.
    """

    action: Action | None = None
    problem: str | None = None  # set instead of `action`: what was wrong with the answer
    thought: str | None = None
    headline: str | None = None  # the thought in a line, for viewers (thought_headline)
    stats: AnswerStats | None = None

    @model_validator(mode="after")
    def _action_or_problem(self) -> Self:
        if (self.action is None) == (self.problem is None):
            raise ValueError("A reply needs either an action or a problem")
        return self


class AgentError(Exception):
    """The agent cannot play any more, for example because its model is unreachable.

    The engine then plays random legal actions for this seat until the match
    ends. The message goes into the event log: no secrets, no prompt text.
    """


class MatchPaused(Exception):
    """The match cannot go on without a decision of the user, for example at a cost cap.

    An agent raises it instead of answering. The engine drops the turn that was
    being played, logs `match_paused` with `reason` and `data`, and
    `Match.run()` raises it on to whoever started the match. `data` goes into
    the event log: plain JSON, no secrets.
    """

    def __init__(self, reason: str, **data: Any):
        super().__init__(reason)
        self.reason = reason
        self.data = data


class Agent(Protocol):
    """Anything that can take a seat: a random bot, a mock LLM or a real model."""

    async def act(self, request: TurnRequest) -> Reply: ...
