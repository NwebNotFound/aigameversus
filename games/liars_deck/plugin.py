"""Liar's Deck: bluff with face-down cards; a caught liar or a wrong caller pulls the trigger.

A round: every living player gets a hand, a table card is drawn, and players
take turns either playing 1-3 cards face down (claiming they are all the table
card) or calling "Liar!" on the previous play. A call reveals only that last
play; the liar, or the wrong caller, pulls the trigger of their own revolver.
Then a new round starts. The last player alive wins.

Hidden information, and who may see it:
- a hand: only its owner (`hand_dealt`);
- which cards were played: only the player who played them (`cards_hidden`),
  until a call reveals them to everyone (`cards_revealed`);
- the live chamber of each revolver: nobody (`revolver_loaded` is for spectators).
"""

import random
from collections.abc import Mapping, Sequence
from typing import Any, Literal

from pydantic import BaseModel

from arena.engine.plugin import GamePlugin, TurnContext
from arena.engine.types import MESSAGE, Action, Event, Placement, PlayerId, ToolSpec, TurnMode
from games.liars_deck.variants import Variant, load_variants

RANKS = ("king", "queen", "ace")
JOKER = "joker"
DEVIL_ID = "DV"  # card id of the devil card (a joker) in the devil-card variant
MAX_TALK_WORDS = 40

_RANK_PREFIX = {"king": "K", "queen": "Q", "ace": "A", JOKER: "J"}


def card_rank(card_id: str) -> str:
    """The rank of a card id such as "K3" (king) or "DV" (the devil card, a joker)."""
    if card_id == DEVIL_ID:
        return JOKER
    return {prefix: rank for rank, prefix in _RANK_PREFIX.items()}[card_id[0]]


def deck_for(variant: Variant) -> list[str]:
    """All card ids of a variant's deck, in a fixed order."""
    counts = {
        "king": variant.deck.kings,
        "queen": variant.deck.queens,
        "ace": variant.deck.aces,
        JOKER: variant.deck.jokers,
    }
    devils = variant.devil_card.count if variant.devil_card else 0
    cards = []
    for rank, count in counts.items():
        plain = count - devils if rank == JOKER else count
        cards += [f"{_RANK_PREFIX[rank]}{n}" for n in range(1, plain + 1)]
    if devils:
        cards.append(DEVIL_ID)
    return cards


def word_count(text: str) -> int:
    return len(text.split())


class Play(BaseModel):
    player: PlayerId
    cards: list[str]


class LiarsState(BaseModel):
    variant: str
    players: list[PlayerId]  # seating order, which is also turn order
    alive: list[PlayerId]
    eliminated: list[list[PlayerId]] = []  # groups, in the order they fell
    live_chambers: dict[PlayerId, list[int]] = {}  # secret: which pulls are live
    pulls: dict[PlayerId, int] = {}
    round_no: int = 0
    table_card: str | None = None
    hands: dict[PlayerId, list[str]] = {}
    current: PlayerId | None = None  # who acts now
    phase: Literal["setup", "turn", "auto_call", "round_over", "over"] = "setup"
    last_play: Play | None = None
    plays_this_round: list[dict[str, Any]] = []  # public: {"player", "count"}
    revealed_this_round: list[dict[str, Any]] = []  # public: {"player", "cards"}
    talked: bool = False  # the current player used table_talk this turn
    next_starter: PlayerId | None = None


def _text_schema(description: str) -> dict[str, Any]:
    return {"type": "string", "description": description, "maxLength": 400}


TABLE_TALK = ToolSpec(
    name="table_talk",
    description=(
        f"Say something to the whole table (at most {MAX_TALK_WORDS} words). "
        "It does not end your turn; you then still play or call. Once per turn."
    ),
    parameters={
        "type": "object",
        "properties": {"text": _text_schema("What you say, at most 40 words.")},
        "required": ["text"],
        "additionalProperties": False,
    },
)

CALL_LIAR = ToolSpec(
    name="call_liar",
    description=(
        "Call 'Liar!' on the previous player's last play instead of playing. Their cards "
        "are revealed: if any is neither the table card nor a joker, they shoot; otherwise you do."
    ),
    parameters={
        "type": "object",
        "properties": {"text": _text_schema("Optional words with the call, at most 40 words.")},
        "additionalProperties": False,
    },
)


def _play_cards_tool(max_cards: int) -> ToolSpec:
    return ToolSpec(
        name="play_cards",
        description=(
            f"Play 1 to {max_cards} cards from your hand face down, claiming they are all "
            "the table card. Use the card ids from your hand."
        ),
        parameters={
            "type": "object",
            "properties": {
                "card_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 1,
                    "maxItems": max_cards,
                    "uniqueItems": True,
                    "description": 'Ids of cards in your hand, for example ["K2", "J1"].',
                },
                "claim_text": _text_schema("Optional words with the play, at most 40 words."),
            },
            "required": ["card_ids"],
            "additionalProperties": False,
        },
    )


class LiarsDeck(GamePlugin[LiarsState]):
    id = "liars_deck"
    name = "Liar's Deck"
    version = "1"
    min_players = 2
    max_players = 4
    # Each round ends with a trigger pull and each revolver has `chambers` pulls,
    # so there are at most players x chambers rounds. A round has at most one play
    # per card dealt (min_cards each) plus the call, each with one table_talk (D-041).
    max_turns = max(
        v.players.max
        * v.revolver.chambers
        * (v.players.max * v.hand_size // v.play.min_cards + 1)
        * 2
        for v in load_variants().values()
    )
    turn_mode = TurnMode.SEQUENTIAL

    def __init__(self) -> None:
        self._variants = load_variants()

    # --- setup -------------------------------------------------------------

    def initial_state(self, players: Sequence[PlayerId], settings: Mapping[str, Any]) -> LiarsState:
        unknown = set(settings) - {"variant"}
        if unknown:
            raise ValueError(f"Unknown settings for liars_deck: {sorted(unknown)}")
        variant_id = settings.get("variant", "base")
        if variant_id not in self._variants:
            raise ValueError(
                f"Unknown variant {variant_id!r}; choose one of {sorted(self._variants)}"
            )
        variant = self._variants[variant_id]
        if not variant.players.min <= len(players) <= variant.players.max:
            raise ValueError(
                f"Variant {variant_id!r} needs {variant.players.min} to "
                f"{variant.players.max} players, got {len(players)}"
            )
        return LiarsState(
            variant=variant_id,
            players=list(players),
            alive=list(players),
            pulls=dict.fromkeys(players, 0),
            hands={player: [] for player in players},
        )

    def setup(self, state: LiarsState, ctx: TurnContext) -> None:
        revolver = self._variant(state).revolver
        for player in state.players:
            live = sorted(
                ctx.rng("revolver", player).sample(range(revolver.chambers), revolver.live)
            )
            ctx.emit("revolver_loaded", {"player": player, "live": live}, visible_to=[])
        self._start_round(state, ctx, starter=state.players[0])

    def _start_round(self, state: LiarsState, ctx: TurnContext, starter: PlayerId) -> None:
        variant = self._variant(state)
        number = state.round_no + 1
        deck = deck_for(variant)
        ctx.rng("deal", number).shuffle(deck)
        table_card = ctx.rng("table_card", number).choice(RANKS)
        size = variant.hand_size
        ctx.emit(
            "round_started",
            {
                "round": number,
                "table_card": table_card,
                "starter": starter,
                "hand_size": size,
                "players": list(state.alive),
            },
        )
        for index, player in enumerate(state.alive):
            hand = deck[index * size : (index + 1) * size]
            ctx.emit("hand_dealt", {"player": player, "cards": hand}, visible_to=[player])

    # --- turns -------------------------------------------------------------

    def active_players(self, state: LiarsState) -> list[PlayerId]:
        return [state.current] if state.phase == "turn" and state.current else []

    def get_tools(self, state: LiarsState, player: PlayerId) -> list[ToolSpec]:
        if state.phase != "turn" or player != state.current:
            return []
        tools = []
        if state.hands[player]:
            tools.append(_play_cards_tool(self._max_cards(state, player)))
        if self._can_call(state, player):
            tools.append(CALL_LIAR)
        if not state.talked:
            tools.append(TABLE_TALK)
        return tools

    def validate(self, state: LiarsState, player: PlayerId, action: Action) -> str | None:
        args = action.arguments
        text = args.get("text") if action.tool != "play_cards" else args.get("claim_text")
        if text is not None and word_count(text) > MAX_TALK_WORDS:
            return f"Your text has {word_count(text)} words; say it in at most {MAX_TALK_WORDS}."
        if action.tool == "play_cards":
            hand = state.hands[player]
            unknown = [card for card in args["card_ids"] if card not in hand]
            if unknown:
                return (
                    f"You do not hold {', '.join(unknown)}. Your hand is {', '.join(hand)}; "
                    "play ids from it."
                )
            if len(args["card_ids"]) > self._max_cards(state, player):
                return f"Play at most {self._max_cards(state, player)} cards."
        if action.tool == "call_liar" and not self._can_call(state, player):
            return "There is no play to call 'Liar!' on yet; play cards instead."
        if action.tool == "table_talk" and state.talked:
            return "You already talked this turn; now play cards or call 'Liar!'."
        return None

    def apply_actions(
        self, state: LiarsState, actions: Mapping[PlayerId, Action], ctx: TurnContext
    ) -> None:
        for player, action in actions.items():
            args = action.arguments
            if action.tool == "table_talk":
                ctx.emit(MESSAGE, {"player": player, "text": args["text"]})
                ctx.emit("talked", {"player": player})
            elif action.tool == "play_cards":
                if args.get("claim_text"):
                    ctx.emit(MESSAGE, {"player": player, "text": args["claim_text"]})
                self._play(state, ctx, player, list(args["card_ids"]))
            elif action.tool == "call_liar":
                if args.get("text"):
                    ctx.emit(MESSAGE, {"player": player, "text": args["text"]})
                self._call(state, ctx, player, automatic=False)

    def step(self, state: LiarsState, ctx: TurnContext) -> None:
        if state.phase == "auto_call" and state.current is not None:
            self._call(state, ctx, state.current, automatic=True)
        if state.phase == "round_over":
            if len(state.alive) <= 1:
                ctx.emit("match_over", {"winner": state.alive[0] if state.alive else None})
            else:
                self._start_round(state, ctx, starter=state.next_starter or state.alive[0])

    def _play(
        self, state: LiarsState, ctx: TurnContext, player: PlayerId, cards: list[str]
    ) -> None:
        ctx.emit("cards_played", {"player": player, "count": len(cards)})
        ctx.emit("cards_hidden", {"player": player, "cards": cards}, visible_to=[player])
        # Who acts next: the next player who still holds cards. If only one player holds
        # cards, that player must check this play (an automatic call). If nobody else holds
        # cards (normal play never gets here), the next living player checks it.
        holders = [p for p in state.alive if state.hands[p]]
        others = [p for p in holders if p != player]
        if not others:
            ctx.emit("turn_passed", {"player": self._next_alive(state, player), "auto_call": True})
        elif len(holders) == 1:
            ctx.emit("turn_passed", {"player": holders[0], "auto_call": True})
        else:
            ctx.emit(
                "turn_passed", {"player": self._next_holder(state, player), "auto_call": False}
            )

    def _call(self, state: LiarsState, ctx: TurnContext, caller: PlayerId, automatic: bool) -> None:
        play = state.last_play
        assert play is not None
        table_card = state.table_card
        honest = all(card_rank(card) in (table_card, JOKER) for card in play.cards)
        devil = DEVIL_ID in play.cards
        ctx.emit(
            "liar_called",
            {"caller": caller, "target": play.player, "automatic": automatic},
        )
        ctx.emit(
            "cards_revealed",
            {"player": play.player, "cards": play.cards, "honest": honest, "devil": devil},
        )
        if devil and self._variant(state).devil_card:
            shooters = [p for p in state.alive if p != play.player]
            reason = "devil_card"
        else:
            shooters = [caller if honest else play.player]
            reason = "wrong_call" if honest else "caught_lying"
        ctx.emit("shooters_chosen", {"players": shooters, "reason": reason})
        fallen = []
        for shooter in shooters:
            pull = state.pulls[shooter]
            live = pull in state.live_chambers[shooter]
            ctx.emit("trigger_pulled", {"player": shooter, "pull": pull + 1, "live": live})
            if live:
                fallen.append(shooter)
        if fallen:
            ctx.emit("players_eliminated", {"players": fallen})
        # The survivor of the duel starts: the shooter if alive, else the other side.
        duel = [shooters[0], play.player if shooters[0] == caller else caller]
        if reason == "devil_card":
            duel = [play.player]
        starter = next((p for p in duel if p in state.alive), None)
        ctx.emit("round_ended", {"round": state.round_no, "next_starter": starter})

    # --- event application ------------------------------------------------

    def apply_event(self, state: LiarsState, event: Event) -> None:
        if event.type == MESSAGE:  # words change nothing in the state
            return
        data = event.data
        match event.type:
            case "revolver_loaded":
                state.live_chambers[data["player"]] = list(data["live"])
            case "round_started":
                state.round_no = data["round"]
                state.table_card = data["table_card"]
                state.current = data["starter"]
                state.phase = "turn"
                state.last_play = None
                state.plays_this_round = []
                state.revealed_this_round = []
                state.talked = False
                state.next_starter = None
                state.hands = {player: [] for player in state.players}
            case "hand_dealt":
                state.hands[data["player"]] = list(data["cards"])
            case "talked":
                state.talked = True
            case "cards_played":
                state.plays_this_round.append({"player": data["player"], "count": data["count"]})
            case "cards_hidden":
                hand = state.hands[data["player"]]
                for card in data["cards"]:
                    hand.remove(card)
                state.last_play = Play(player=data["player"], cards=list(data["cards"]))
            case "turn_passed":
                state.current = data["player"]
                state.talked = False
                state.phase = "auto_call" if data["auto_call"] else "turn"
            case "liar_called":
                state.current = None
            case "cards_revealed":
                state.revealed_this_round.append(
                    {"player": data["player"], "cards": list(data["cards"])}
                )
            case "shooters_chosen":
                pass
            case "trigger_pulled":
                state.pulls[data["player"]] += 1
            case "players_eliminated":
                state.alive = [p for p in state.alive if p not in data["players"]]
                state.eliminated.append(list(data["players"]))
            case "round_ended":
                state.phase = "round_over"
                state.next_starter = data["next_starter"]
            case "match_over":
                state.phase = "over"
                state.current = None
            case unknown:
                raise ValueError(f"Unknown liars_deck event: {unknown}")

    # --- views -------------------------------------------------------------

    def get_observation(self, state: LiarsState, player: PlayerId) -> dict[str, Any]:
        variant = self._variant(state)
        observation: dict[str, Any] = {
            "you": player,
            "variant": state.variant,
            "round": state.round_no,
            "table_card": state.table_card,
            "hand": list(state.hands.get(player, [])),
            "your_turn": state.phase == "turn" and state.current == player,
            "turn": state.current,
            "max_cards_per_play": variant.play.max_cards,
            "players": [
                {
                    "id": p,
                    "alive": p in state.alive,
                    "cards": len(state.hands.get(p, [])),
                    "trigger_pulls": state.pulls[p],
                    "chambers": variant.revolver.chambers,
                }
                for p in state.players
            ],
            "last_play": (
                {"player": state.last_play.player, "count": len(state.last_play.cards)}
                if state.last_play
                else None
            ),
            "plays_this_round": [dict(p) for p in state.plays_this_round],
            "revealed_this_round": [
                {"player": r["player"], "cards": list(r["cards"])}
                for r in state.revealed_this_round
            ],
        }
        if variant.devil_card:
            observation["devil_card_id"] = DEVIL_ID
        return observation

    def render_spec(self, state: LiarsState) -> dict[str, Any]:
        """What a spectator view draws: a card table, with every hand (spectators may see all).

        Not part of the plugin interface yet (D-033); the UI will define it in phase 5.
        """
        variant = self._variant(state)
        return {
            "layout": "card_table",
            "round": state.round_no,
            "table_card": state.table_card,
            "turn": state.current,
            "seats": [
                {
                    "player": p,
                    "alive": p in state.alive,
                    "hand": list(state.hands.get(p, [])),
                    "trigger_pulls": state.pulls[p],
                    "chambers": variant.revolver.chambers,
                }
                for p in state.players
            ],
            "last_play": state.last_play.model_dump() if state.last_play else None,
        }

    # --- end ---------------------------------------------------------------

    def is_over(self, state: LiarsState) -> bool:
        return state.phase == "over"

    def results(self, state: LiarsState) -> list[Placement]:
        """The survivor wins; then the players in reverse order of elimination.

        Players eliminated by the same shot share a rank.
        """
        placements = [Placement(player=p, rank=1) for p in state.alive]
        rank = len(state.alive) + 1
        for group in reversed(state.eliminated):
            placements += [Placement(player=p, rank=rank) for p in group]
            rank += len(group)
        return placements

    def random_action(
        self, observation: Mapping[str, Any], tools: Sequence[ToolSpec], rng: random.Random
    ) -> Action:
        names = {tool.name for tool in tools}
        hand = observation["hand"]
        can_play = "play_cards" in names and hand
        if "call_liar" in names and (not can_play or rng.random() < 0.35):
            return Action(tool="call_liar", arguments={})
        if can_play:
            count = rng.randint(1, min(observation["max_cards_per_play"], len(hand)))
            return Action(tool="play_cards", arguments={"card_ids": rng.sample(hand, count)})
        return Action(tool="table_talk", arguments={"text": "..."})

    # --- helpers -----------------------------------------------------------

    def _variant(self, state: LiarsState) -> Variant:
        return self._variants[state.variant]

    def _max_cards(self, state: LiarsState, player: PlayerId) -> int:
        return min(self._variant(state).play.max_cards, len(state.hands[player]))

    def _can_call(self, state: LiarsState, player: PlayerId) -> bool:
        return state.last_play is not None and state.last_play.player != player

    def _next_alive(self, state: LiarsState, player: PlayerId) -> PlayerId:
        order = state.players
        start = order.index(player)
        for offset in range(1, len(order) + 1):
            candidate = order[(start + offset) % len(order)]
            if candidate in state.alive and candidate != player:
                return candidate
        return player

    def _next_holder(self, state: LiarsState, player: PlayerId) -> PlayerId:
        order = state.players
        start = order.index(player)
        for offset in range(1, len(order)):
            candidate = order[(start + offset) % len(order)]
            if candidate in state.alive and state.hands[candidate]:
                return candidate
        raise AssertionError("no other player holds cards")
