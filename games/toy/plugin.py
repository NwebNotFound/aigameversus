"""High Card.

Every player gets a hand of secret, distinct number cards. Each trick, players
play one card in turn; the highest card wins the trick and its player leads the
next one. Whoever wins the most tricks wins.

Small on purpose, but it uses everything a real game needs: hidden
information, seeded randomness, turn order, rule validation and standings.
"""

import random
from collections.abc import Mapping, Sequence
from typing import Any

from pydantic import BaseModel

from arena.engine.plugin import GamePlugin, TurnContext
from arena.engine.types import Action, Event, Placement, PlayerId, ToolSpec, TurnMode

DEFAULT_HAND_SIZE = 3
MAX_HAND_SIZE = 5

PLAY_CARD = ToolSpec(
    name="play_card",
    description="Play one card from your hand into the current trick.",
    parameters={
        "type": "object",
        "properties": {"card": {"type": "integer", "description": "A card from your hand."}},
        "required": ["card"],
        "additionalProperties": False,
    },
)


class ToyState(BaseModel):
    players: list[PlayerId]
    hand_size: int
    hands: dict[PlayerId, list[int]]
    leader: PlayerId  # leads the current trick
    trick: dict[PlayerId, int]  # cards played in the current trick
    tricks_won: dict[PlayerId, int]
    tricks_played: int = 0


class ToyGame(GamePlugin[ToyState]):
    id = "toy"
    name = "High Card"
    version = "1"
    min_players = 2
    max_players = 4
    turn_mode = TurnMode.SEQUENTIAL
    max_turns = max_players * MAX_HAND_SIZE  # every turn plays one card

    def initial_state(self, players: Sequence[PlayerId], settings: Mapping[str, Any]) -> ToyState:
        unknown = set(settings) - {"hand_size"}
        if unknown:
            raise ValueError(f"Unknown settings for toy: {sorted(unknown)}")
        hand_size = settings.get("hand_size", DEFAULT_HAND_SIZE)
        if not isinstance(hand_size, int) or not 1 <= hand_size <= MAX_HAND_SIZE:
            raise ValueError(f"hand_size must be an integer from 1 to {MAX_HAND_SIZE}")
        return ToyState(
            players=list(players),
            hand_size=hand_size,
            hands={player: [] for player in players},
            leader=players[0],
            trick={},
            tricks_won={player: 0 for player in players},
        )

    def setup(self, state: ToyState, ctx: TurnContext) -> None:
        deck = list(range(1, len(state.players) * state.hand_size + 1))
        ctx.rng("deal").shuffle(deck)
        for seat, player in enumerate(state.players):
            cards = sorted(deck[seat * state.hand_size : (seat + 1) * state.hand_size])
            ctx.emit("hand_dealt", {"player": player, "cards": cards}, visible_to=[player])

    def active_players(self, state: ToyState) -> list[PlayerId]:
        first = state.players.index(state.leader)
        order = state.players[first:] + state.players[:first]
        return [player for player in order if player not in state.trick][:1]

    def get_observation(self, state: ToyState, player: PlayerId) -> dict[str, Any]:
        return {
            "hand": list(state.hands[player]),
            "trick": dict(state.trick),
            "leader": state.leader,
            "tricks_won": dict(state.tricks_won),
            "cards_left": {other: len(hand) for other, hand in state.hands.items()},
        }

    def get_tools(self, state: ToyState, player: PlayerId) -> list[ToolSpec]:
        return [PLAY_CARD]

    def validate(self, state: ToyState, player: PlayerId, action: Action) -> str | None:
        card = action.arguments["card"]
        hand = state.hands[player]
        if card not in hand:
            return f"Card {card} is not in your hand. Your hand: {hand}."
        return None

    def apply_actions(
        self, state: ToyState, actions: Mapping[PlayerId, Action], ctx: TurnContext
    ) -> None:
        for player, action in actions.items():
            ctx.emit("card_played", {"player": player, "card": action.arguments["card"]})

    def step(self, state: ToyState, ctx: TurnContext) -> None:
        if len(state.trick) == len(state.players):
            winner = max(state.trick, key=state.trick.__getitem__)
            ctx.emit("trick_won", {"player": winner, "cards": dict(state.trick)})

    def apply_event(self, state: ToyState, event: Event) -> None:
        data = event.data
        match event.type:
            case "hand_dealt":
                state.hands[data["player"]] = list(data["cards"])
            case "card_played":
                state.hands[data["player"]].remove(data["card"])
                state.trick[data["player"]] = data["card"]
            case "trick_won":
                state.tricks_won[data["player"]] += 1
                state.tricks_played += 1
                state.leader = data["player"]
                state.trick = {}
            case unknown:
                raise ValueError(f"Unknown toy event: {unknown}")

    def is_over(self, state: ToyState) -> bool:
        return state.tricks_played == state.hand_size

    def results(self, state: ToyState) -> list[Placement]:
        won = state.tricks_won
        return [
            Placement(player=player, rank=1 + sum(other > won[player] for other in won.values()))
            for player in state.players
        ]

    def random_action(
        self, observation: Mapping[str, Any], tools: Sequence[ToolSpec], rng: random.Random
    ) -> Action:
        return Action(tool="play_card", arguments={"card": rng.choice(observation["hand"])})
