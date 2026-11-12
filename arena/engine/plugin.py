"""The interface every game implements."""

import random
from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping, Sequence
from importlib import resources
from typing import Any, ClassVar

from pydantic import BaseModel

from arena.engine.types import Action, Event, EventSource, Placement, PlayerId, ToolSpec, TurnMode


class TurnContext:
    """What a plugin may use while it changes the game: random streams and `emit`."""

    def __init__(
        self,
        stream: Callable[..., random.Random],
        record: Callable[[Event], None],
    ):
        self._stream = stream
        self._record = record

    def rng(self, *key: str | int) -> random.Random:
        """The random stream named by `key`, derived from the match seed.

        Name each use after what it decides, including a counter that changes
        between uses, for example `ctx.rng("deal", state.round_no)`. Asking for
        the same key twice in a match is an error, because it would repeat the
        same numbers.
        """
        return self._stream(*key)

    def emit(
        self,
        type: str,
        data: Mapping[str, Any] | None = None,
        *,
        visible_to: Sequence[PlayerId] | None = None,
    ) -> None:
        """Record a game event and apply it to the state at once.

        `visible_to=None` is public. A list restricts the event to those
        players; an empty list hides it from all players (spectators only).

        Text a player wrote goes out as `emit(MESSAGE, {"player": author,
        "text": words})` and in no other event, so that prompts can show it as
        that player's words.
        """
        self._record(
            Event(
                source=EventSource.GAME,
                type=type,
                data=dict(data or {}),
                visible_to=None if visible_to is None else tuple(visible_to),
            )
        )


class GamePlugin[StateT: BaseModel](ABC):
    """Rules of one game.

    The contract that makes replays work: the state changes only inside
    `apply_event`. `setup`, `apply_actions` and `step` decide what happens and
    call `ctx.emit`; they never touch the state directly. Replaying the game
    events of a log over `initial_state` therefore rebuilds the exact state.

    Game logic is deterministic. Randomness comes only from `ctx.rng`. A
    plugin never calls a model and never reads the network or files outside
    its own package.
    """

    id: ClassVar[str]
    name: ClassVar[str]  # the title players and spectators read; the only place it is written
    version: ClassVar[str]  # bump when rules or data change; keep the old in at_version (D-139)
    min_players: ClassVar[int]
    max_players: ClassVar[int]
    turn_mode: ClassVar[TurnMode]
    # No match of the game takes more turns than this; the engine stops one that
    # does. Set it to what the rules allow at most, with room to spare.
    max_turns: ClassVar[int] = 10_000

    def at_version(self, version: str) -> "GamePlugin[StateT]":
        """This game with the rules of `version`, as a log recorded with it needs them.

        A stored match keeps its rules: replays, boards and analytics of a log ask for
        the version in its `match_started`. A game that changed its rules keeps the old
        versions it can still play and overrides this; the default knows only its own.
        Raises ValueError for a version the game does not have.
        """
        if version != self.version:
            raise ValueError(f"{self.id} has no rules version {version} (it is {self.version})")
        return self

    def rules(self, settings: Mapping[str, Any] | None = None) -> str:
        """The rule summary a model gets in its prompt: `rules.md` next to the plugin.

        A game with several prompt versions picks the text by `settings`.
        """
        package = type(self).__module__.rpartition(".")[0]
        return resources.files(package).joinpath("rules.md").read_text(encoding="utf-8")

    def prompt_version(self, settings: Mapping[str, Any] | None = None) -> str:
        """Which prompt the models of a match get; recorded in `match_started`."""
        return "v1"

    def history_limit(self, settings: Mapping[str, Any] | None = None) -> int:
        """How many of the latest events a prompt shows (the older ones are only counted).

        A game in which one turn can produce more than this for a player (a simultaneous game
        with talk) raises it for a prompt version, so nothing of the turn is dropped.
        """
        return 40

    def situation_summary(
        self, observation: Mapping[str, Any], settings: Mapping[str, Any] | None = None
    ) -> str | None:
        """A short text about the turn for the top of the prompt, or None for none.

        Build it from `observation` only: it is that player's view.
        """
        return None

    @abstractmethod
    def initial_state(self, players: Sequence[PlayerId], settings: Mapping[str, Any]) -> StateT:
        """The state before anything happened. No randomness.

        Raises ValueError if the settings are not valid for this game.
        """

    @abstractmethod
    def setup(self, state: StateT, ctx: TurnContext) -> None:
        """Emit the opening events, for example dealing cards or assigning roles."""

    @abstractmethod
    def active_players(self, state: StateT) -> list[PlayerId]:
        """Players who must act now. May be empty when only `step` is due."""

    @abstractmethod
    def get_observation(self, state: StateT, player: PlayerId) -> dict[str, Any]:
        """Everything this player may see, and nothing else. Must not alias the state."""

    @abstractmethod
    def get_tools(self, state: StateT, player: PlayerId) -> list[ToolSpec]:
        """The actions this player may take now."""

    @abstractmethod
    def validate(self, state: StateT, player: PlayerId, action: Action) -> str | None:
        """Check an action against the rules.

        Called after the engine has checked the tool name and the argument
        schema. Returns None if the action is legal, otherwise a message that
        tells the player what is wrong and how to fix it.
        """

    @abstractmethod
    def apply_actions(
        self, state: StateT, actions: Mapping[PlayerId, Action], ctx: TurnContext
    ) -> None:
        """Emit the events caused by validated actions, one per active player."""

    @abstractmethod
    def step(self, state: StateT, ctx: TurnContext) -> None:
        """Emit whatever is due without a player decision, such as closing a round.

        Called after every `apply_actions` and whenever no player is active.
        """

    @abstractmethod
    def apply_event(self, state: StateT, event: Event) -> None:
        """Apply one game event to the state. The only place that mutates it."""

    @abstractmethod
    def is_over(self, state: StateT) -> bool: ...

    @abstractmethod
    def results(self, state: StateT) -> list[Placement]:
        """Final standings of all players, once the game is over."""

    @abstractmethod
    def random_action(
        self, observation: Mapping[str, Any], tools: Sequence[ToolSpec], rng: random.Random
    ) -> Action:
        """A random legal action, chosen from what the player can see.

        This is the game's random bot. The engine also uses it as the fallback
        when a player fails to produce a legal action.
        """
