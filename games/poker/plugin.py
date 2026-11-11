"""Poker: No-Limit Texas Hold'em as a tournament for 2-6 players.

Everyone starts with the same stack. Blinds double every few hands, the
button moves every hand, and the match ends when one player holds all the
chips or after the hand limit, when the biggest stack wins.

Hidden information, and who may see it:
- hole cards: only their owner (`hole_dealt`), until a showdown reveals them;
- the shuffled deck: nobody (`deck_shuffled` is for spectators).

Betting rules live in `betting.py`; hand strength in `evaluator.py`.
"""

import random
from collections.abc import Mapping, Sequence
from typing import Any, Literal

from pydantic import BaseModel

from arena.engine.plugin import GamePlugin, TurnContext
from arena.engine.rng import derive_rng
from arena.engine.types import MESSAGE, Action, Event, Placement, PlayerId, ToolSpec, TurnMode
from games.poker import prompt
from games.poker.betting import Street, side_pots, split
from games.poker.cards import Card, Deck
from games.poker.evaluator import best_hand, win_probabilities

STREETS = ("preflop", "flop", "turn", "river")
BOARD_CARDS = {"flop": 3, "turn": 1, "river": 1}
MAX_TALK_WORDS = 40
DEFAULTS = {"starting_stack": 1000, "small_blind": 10, "double_every": 10, "hand_limit": 100}

BetKind = Literal["fold", "check", "call", "raise", "all_in"]


def turn_bound(
    players: int, starting_stack: int, small_blind: int, double_every: int, hand_limit: int
) -> int:
    """The most turns a tournament with these settings can take (D-045).

    Per hand, every street starts with at most one action per player, and every
    raise lets at most all others act again. A full raise lifts the bet by at
    least the big blind, so a hand has at most chips / big blind of them, plus
    one short all-in per player. Each action may come with one table_talk turn.
    """
    chips = players * starting_stack
    total = 0
    for hand in range(1, hand_limit + 1):
        big_blind = 2 * small_blind * 2 ** ((hand - 1) // double_every)
        raises = chips // big_blind + players
        actions = len(STREETS) * players + raises * (players - 1)
        total += 2 * actions
    return total


class Stats(BaseModel):
    """What every player can know about an opponent's play so far."""

    hands: int = 0
    voluntarily_played: int = 0  # hands where they called or raised before the flop
    raises: int = 0
    showdowns: int = 0
    shown_bluffs: int = 0  # made the last bet or raise of a hand and lost the showdown


class PokerState(BaseModel):
    players: list[PlayerId]
    seats: list[PlayerId]  # seating order; the button moves along it
    starting_stack: int
    base_small_blind: int
    double_every: int
    hand_limit: int
    deck_seed: int | None = None  # duplicate mode: cards come from this seed, not the match seed
    stacks: dict[PlayerId, int] = {}
    hand_no: int = 0
    button: PlayerId | None = None
    small_blind: int = 0
    big_blind: int = 0
    in_hand: list[PlayerId] = []  # dealt into the current hand, in seat order
    hole: dict[PlayerId, list[str]] = {}
    deck: list[str] = []  # undealt cards of this hand (spectators only)
    board: list[str] = []
    street_name: str | None = None
    street: Street | None = None
    contributions: dict[PlayerId, int] = {}  # chips each player put in this hand
    posted: dict[PlayerId, int] = {}  # blinds waiting for the preflop round
    folded: list[PlayerId] = []
    phase: Literal["setup", "betting", "hand_over", "over"] = "setup"
    actions: list[dict[str, Any]] = []  # public actions of this hand
    talked: bool = False
    aggressor: PlayerId | None = None
    started_with: dict[PlayerId, int] = {}  # stacks at the start of the hand
    eliminated: list[list[tuple[PlayerId, int]]] = []  # per hand: (player, chips at its start)
    stats: dict[PlayerId, Stats] = {}


def word_count(text: str) -> int:
    return len(text.split())


def _text(description: str) -> dict[str, Any]:
    return {"type": "string", "description": description, "maxLength": 400}


def _tool(name: str, description: str, properties: dict | None = None, required=()) -> ToolSpec:
    return ToolSpec(
        name=name,
        description=description,
        parameters={
            "type": "object",
            "properties": properties or {},
            "required": list(required),
            "additionalProperties": False,
        },
    )


FOLD = _tool("fold", "Give up this hand and the chips you have bet in it.")
CHECK = _tool("check", "Pass without betting; only possible when there is no bet to call.")
ALL_IN = _tool("all_in", "Bet all your chips.")
TABLE_TALK = _tool(
    "table_talk",
    f"Say something to the table (at most {MAX_TALK_WORDS} words). It does not end your turn; "
    "you then still act. Once per turn.",
    {"text": _text("What you say, at most 40 words.")},
    required=["text"],
)


def _call_tool(amount: int) -> ToolSpec:
    return _tool("call", f"Match the current bet: add {amount} chips.")


def _raise_tool(low: int, high: int) -> ToolSpec:
    return _tool(
        "raise",
        f"Raise to a total bet of `amount` chips this betting round, from {low} to {high}.",
        {"amount": {"type": "integer", "minimum": low, "maximum": high}},
        required=["amount"],
    )


class Poker(GamePlugin[PokerState]):
    id = "poker"
    name = "Poker"
    version = "1"
    min_players = 2
    max_players = 6
    max_turns = turn_bound(6, **DEFAULTS)
    turn_mode = TurnMode.SEQUENTIAL

    # --- the prompt ----------------------------------------------------------

    def prompt_version(self, settings: Mapping[str, Any] | None = None) -> str:
        """The prompt version of a match, recorded with it (see `prompt.py` next to this file)."""
        return prompt.version_of(settings)

    def rules(self, settings: Mapping[str, Any] | None = None) -> str:
        return prompt.rules_text(prompt.version_of(settings))

    def situation_summary(
        self, observation: Mapping[str, Any], settings: Mapping[str, Any] | None = None
    ) -> str | None:
        """A short text for the top of the turn's prompt; only version p2 has one."""
        if prompt.version_of(settings) == "poker-p1":
            return None
        return prompt.situation_summary(observation)

    # --- setup -------------------------------------------------------------

    def initial_state(self, players: Sequence[PlayerId], settings: Mapping[str, Any]) -> PokerState:
        unknown = set(settings) - {*DEFAULTS, "duplicate", "prompt_version"}
        if unknown:
            raise ValueError(f"Unknown settings for poker: {sorted(unknown)}")
        prompt.version_of(settings)  # refuses an unknown prompt version
        values = {key: settings.get(key, default) for key, default in DEFAULTS.items()}
        for key, value in values.items():
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                raise ValueError(f"{key} must be a whole number of at least 1, got {value!r}")
        if values["starting_stack"] < 2 * values["small_blind"]:
            raise ValueError("starting_stack must cover at least one big blind")
        bound = turn_bound(len(players), **values)
        if bound > self.max_turns:
            raise ValueError(
                f"These settings allow up to {bound} turns, more than Poker's limit of "
                f"{self.max_turns}; use fewer hands, smaller stacks or bigger blinds"
            )
        seats, deck_seed = list(players), None
        duplicate = settings.get("duplicate")
        if duplicate is not None:
            if not isinstance(duplicate, dict) or set(duplicate) != {"deck_seed", "rotation"}:
                raise ValueError("duplicate needs exactly {deck_seed, rotation}")
            if not all(isinstance(duplicate[k], int) for k in duplicate):
                raise ValueError("duplicate deck_seed and rotation must be whole numbers")
            shift = duplicate["rotation"] % len(seats)
            seats = seats[shift:] + seats[:shift]
            deck_seed = duplicate["deck_seed"]
        return PokerState(
            players=list(players),
            seats=seats,
            starting_stack=values["starting_stack"],
            base_small_blind=values["small_blind"],
            double_every=values["double_every"],
            hand_limit=values["hand_limit"],
            deck_seed=deck_seed,
            stacks=dict.fromkeys(players, values["starting_stack"]),
            stats={player: Stats() for player in players},
        )

    def setup(self, state: PokerState, ctx: TurnContext) -> None:
        self._start_hand(state, ctx)

    def _start_hand(self, state: PokerState, ctx: TurnContext) -> None:
        number = state.hand_no + 1
        level = (number - 1) // state.double_every
        small = state.base_small_blind * 2**level
        big = 2 * small
        seated = [p for p in state.seats if state.stacks[p] > 0]
        button = (
            seated[0] if state.button is None else self._next_in(state.seats, seated, state.button)
        )
        order = self._from(seated, button)  # button first
        heads_up = len(seated) == 2
        sb_player, bb_player = (order[0], order[1]) if heads_up else (order[1], order[2])
        if state.deck_seed is None:
            rng = ctx.rng("deck", number)
        else:  # duplicate mode: the same cards for the same hand, whoever sits where
            rng = derive_rng(state.deck_seed, "poker-deck", number)
        cards = [str(card) for card in Deck(rng).deal(52)]
        ctx.emit(
            "hand_started",
            {
                "hand": number,
                "button": button,
                "small_blind_player": sb_player,
                "big_blind_player": bb_player,
                "small_blind": small,
                "big_blind": big,
                "players": seated,
            },
        )
        ctx.emit("deck_shuffled", {"cards": cards}, visible_to=[])
        # Hole cards go out by seat position, so duplicate matches give a seat the same cards.
        for index, player in enumerate(seated):
            ctx.emit(
                "hole_dealt",
                {"player": player, "cards": cards[2 * index : 2 * index + 2]},
                visible_to=[player],
            )
        for player, amount, kind in ((sb_player, small, "small"), (bb_player, big, "big")):
            posted = min(amount, state.stacks[player])
            ctx.emit("blind_posted", {"player": player, "amount": posted, "kind": kind})
        preflop = self._from(seated, bb_player)[1:] + [bb_player]
        if heads_up:
            preflop = [button, bb_player]
        ctx.emit("street_started", {"street": "preflop", "order": preflop, "cards": []})

    # --- turns -------------------------------------------------------------

    def active_players(self, state: PokerState) -> list[PlayerId]:
        if state.phase != "betting" or state.street is None:
            return []
        actor = state.street.next_actor()
        return [actor] if actor else []

    def get_tools(self, state: PokerState, player: PlayerId) -> list[ToolSpec]:
        if player not in self.active_players(state):
            return []
        legal = state.street.legal(player)
        tools = [FOLD, CHECK if legal.can_check else _call_tool(legal.call_amount)]
        if legal.min_raise_to is not None:
            tools.append(_raise_tool(legal.min_raise_to, legal.max_raise_to))
        if state.street.stacks[player] > 0 and state.street.problem(player, "all_in") is None:
            tools.append(ALL_IN)  # not after a short all-in when it would be a raise
        if not state.talked:
            tools.append(TABLE_TALK)
        return tools

    def validate(self, state: PokerState, player: PlayerId, action: Action) -> str | None:
        if action.tool == "table_talk":
            if state.talked:
                return "You already talked this turn; now fold, check, call, raise or go all in."
            words = word_count(action.arguments["text"])
            if words > MAX_TALK_WORDS:
                return f"Your text has {words} words; say it in at most {MAX_TALK_WORDS}."
            return None
        return state.street.problem(player, action.tool, action.arguments.get("amount"))

    def apply_actions(
        self, state: PokerState, actions: Mapping[PlayerId, Action], ctx: TurnContext
    ) -> None:
        for player, action in actions.items():
            if action.tool == "table_talk":
                ctx.emit(MESSAGE, {"player": player, "text": action.arguments["text"]})
                ctx.emit("talked", {"player": player})
                continue
            street = state.street
            kind = action.tool
            before = street.bets[player]
            target = {
                "fold": before,
                "check": before,
                "call": min(street.current_bet, before + street.stacks[player]),
                "all_in": before + street.stacks[player],
                "raise": action.arguments.get("amount"),
            }[kind]
            ctx.emit(
                "bet_action",
                {
                    "player": player,
                    "kind": kind,
                    "street": state.street_name,
                    "to": target,
                    "added": target - before,
                },
            )
        self._progress(state, ctx)

    def step(self, state: PokerState, ctx: TurnContext) -> None:
        self._progress(state, ctx)

    def _progress(self, state: PokerState, ctx: TurnContext) -> None:
        """Run everything that needs no decision until a player must act or the match ends."""
        while True:
            if state.phase == "betting":
                street = state.street
                live = [p for p in state.in_hand if p not in state.folded]
                if len(live) == 1:
                    self._award(state, ctx, showdown=False)
                elif street.next_actor() is not None:
                    return
                elif state.street_name == "river":
                    self._award(state, ctx, showdown=True)
                else:
                    following = STREETS[STREETS.index(state.street_name) + 1]
                    count = BOARD_CARDS[following]
                    cards = state.deck[:count]
                    order = [
                        p for p in self._from(state.in_hand, state.button)[1:] + [state.button]
                    ]
                    ctx.emit(
                        "street_started", {"street": following, "order": order, "cards": cards}
                    )
            elif state.phase == "hand_over":
                self._finish_hand(state, ctx)
            else:
                return

    def _award(self, state: PokerState, ctx: TurnContext, *, showdown: bool) -> None:
        live = [p for p in state.in_hand if p not in state.folded]
        values = {}
        if showdown:
            board = [Card.parse(card) for card in state.board]
            values = {p: best_hand([*map(Card.parse, state.hole[p]), *board]) for p in live}
            ctx.emit(
                "showdown",
                {
                    "hands": [
                        {
                            "player": p,
                            "cards": list(state.hole[p]),
                            "hand": values[p].category.name.lower(),
                        }
                        for p in live
                    ]
                },
            )
        left_of_button = self._from(state.in_hand, state.button)[1:] + [state.button]
        for pot in side_pots(
            {p: state.contributions.get(p, 0) for p in state.in_hand}, state.folded
        ):
            if showdown and len(pot.eligible) > 1:
                best = max(values[p] for p in pot.eligible)
                winners = [p for p in left_of_button if p in pot.eligible and values[p] == best]
            else:
                winners = [p for p in left_of_button if p in pot.eligible]
            ctx.emit(
                "pot_awarded",
                {
                    "amount": pot.amount,
                    "eligible": list(pot.eligible),
                    "shares": split(pot.amount, winners),
                },
            )
        ctx.emit("hand_ended", {"hand": state.hand_no, "showdown": showdown})

    def _finish_hand(self, state: PokerState, ctx: TurnContext) -> None:
        busted = [p for p in state.in_hand if state.stacks[p] == 0]
        if busted:
            # More chips at the start of the hand places higher among those who fell together.
            busted.sort(key=lambda p: -state.started_with[p])
            ctx.emit(
                "players_eliminated",
                {"players": busted, "started_with": [state.started_with[p] for p in busted]},
            )
        alive = [p for p in state.seats if state.stacks[p] > 0]
        if len(alive) == 1:
            ctx.emit("match_over", {"reason": "last_player", "winner": alive[0]})
        elif state.hand_no >= state.hand_limit:
            ctx.emit("match_over", {"reason": "hand_limit", "winner": None})
        else:
            self._start_hand(state, ctx)

    # --- event application ------------------------------------------------

    def apply_event(self, state: PokerState, event: Event) -> None:
        if event.type == MESSAGE:  # words change nothing in the state
            return
        data = event.data
        match event.type:
            case "hand_started":
                state.hand_no = data["hand"]
                state.button = data["button"]
                state.small_blind = data["small_blind"]
                state.big_blind = data["big_blind"]
                state.in_hand = list(data["players"])
                state.hole = {}
                state.board = []
                state.contributions = dict.fromkeys(state.in_hand, 0)
                state.posted = {}
                state.folded = []
                state.actions = []
                state.street = None
                state.street_name = None
                state.aggressor = None
                state.talked = False
                state.started_with = {p: state.stacks[p] for p in state.in_hand}
                state.phase = "betting"
                for player in state.in_hand:
                    state.stats[player].hands += 1
            case "deck_shuffled":
                state.deck = list(data["cards"])
            case "hole_dealt":
                state.hole[data["player"]] = list(data["cards"])
                for card in data["cards"]:
                    state.deck.remove(card)
            case "blind_posted":
                player, amount = data["player"], data["amount"]
                state.stacks[player] -= amount
                state.contributions[player] += amount
                state.posted[player] = state.posted.get(player, 0) + amount
                state.actions.append(dict(data, action="blind"))
            case "street_started":
                for card in data["cards"]:
                    state.deck.remove(card)
                state.board += data["cards"]
                state.street_name = data["street"]
                all_in = [p for p in state.in_hand if state.stacks[p] == 0]
                state.street = Street.open(
                    data["order"],
                    {p: state.stacks[p] for p in data["order"]},
                    big_blind=state.big_blind,
                    posted=state.posted if data["street"] == "preflop" else None,
                    folded=[p for p in data["order"] if p in state.folded],
                    all_in=all_in,
                )
                state.posted = {}
                state.talked = False
            case "talked":
                state.talked = True
            case "bet_action":
                player, kind = data["player"], data["kind"]
                raised = data["to"] > state.street.current_bet
                added = state.street.apply(player, kind, data["to"] if kind == "raise" else None)
                if added != data["added"]:
                    raise ValueError(
                        f"bet_action says {data['added']} chips, the rules give {added}"
                    )
                state.stacks[player] -= added
                state.contributions[player] += added
                state.talked = False
                if kind == "fold":
                    state.folded.append(player)
                if raised:
                    state.aggressor = player
                if kind == "raise":
                    state.stats[player].raises += 1
                if data["street"] == "preflop" and kind in ("call", "raise", "all_in"):
                    flags = state.actions
                    already = any(a.get("player") == player and a.get("voluntary") for a in flags)
                    if not already:
                        state.stats[player].voluntarily_played += 1
                    state.actions.append(dict(data, action="bet", voluntary=True))
                else:
                    state.actions.append(dict(data, action="bet"))
            case "showdown":
                for shown in data["hands"]:
                    state.stats[shown["player"]].showdowns += 1
            case "pot_awarded":
                for player, amount in data["shares"].items():
                    state.stacks[player] += amount
            case "hand_ended":
                if data["showdown"] and state.aggressor and state.aggressor not in self._won(state):
                    state.stats[state.aggressor].shown_bluffs += 1
                state.contributions = dict.fromkeys(state.in_hand, 0)
                state.street = None
                state.phase = "hand_over"
            case "players_eliminated":
                state.eliminated.append(
                    [
                        (p, start)
                        for p, start in zip(data["players"], data["started_with"], strict=True)
                    ]
                )
            case "match_over":
                state.phase = "over"
            case unknown:
                raise ValueError(f"Unknown poker event: {unknown}")

    def _won(self, state: PokerState) -> set[PlayerId]:
        """Players whose stack grew during the hand that just ended."""
        return {p for p in state.in_hand if state.stacks[p] > state.started_with[p]}

    # --- views -------------------------------------------------------------

    def get_observation(self, state: PokerState, player: PlayerId) -> dict[str, Any]:
        street = state.street
        legal = street.legal(player) if street and player in street.order else None
        pots = (
            side_pots({p: state.contributions.get(p, 0) for p in state.in_hand}, state.folded)
            if any(state.contributions.values())
            else []
        )
        your_turn = player in self.active_players(state)
        return {
            "you": player,
            "hand": state.hand_no,
            "hand_limit": state.hand_limit,
            "blinds": {
                "small": state.small_blind,
                "big": state.big_blind,
                "double_after_hand": ((state.hand_no - 1) // state.double_every + 1)
                * state.double_every,
            },
            "your_cards": list(state.hole.get(player, [])),
            "board": list(state.board),
            "street": state.street_name,
            "pot": sum(state.contributions.values()),
            "pots": [{"amount": p.amount, "eligible": list(p.eligible)} for p in pots],
            "players": [
                {
                    "id": p,
                    "stack": state.stacks[p],
                    "bet": street.bets.get(p, 0) if street else 0,
                    "in_hand": p in state.in_hand and p not in state.folded,
                    "all_in": p in state.in_hand and state.stacks[p] == 0,
                    "position": self._position(state, p),
                }
                for p in state.seats
            ],
            "your_turn": your_turn,
            "to_call": legal.call_amount if legal and your_turn else 0,
            "min_raise_to": legal.min_raise_to if legal and your_turn else None,
            "max_raise_to": legal.max_raise_to if legal and your_turn else None,
            "actions_this_hand": [
                {k: v for k, v in a.items() if k != "voluntary"} for a in state.actions
            ],
            "opponents": {p: state.stats[p].model_dump() for p in state.players if p != player},
        }

    def render_spec(self, state: PokerState) -> dict[str, Any]:
        """What a spectator view draws: the table with every hole card (spectators may see all).

        Not part of the plugin interface yet (D-039); the UI will define it in phase 5.
        """
        chances = self._win_chances(state)
        return {
            "layout": "poker_table",
            "hand": state.hand_no,
            "street": state.street_name,
            "board": list(state.board),
            "pot": sum(state.contributions.values()),
            "side_pots": self._pots(state),
            "button": state.button,
            "seats": [
                {
                    "player": p,
                    "stack": state.stacks[p],
                    "cards": list(state.hole.get(p, [])),
                    "folded": p in state.folded,
                    "position": self._position(state, p),
                    "win_probability": chances.get(p),
                }
                for p in state.seats
            ],
        }

    def _pots(self, state: PokerState) -> list[dict[str, Any]]:
        """The main pot and side pots as they stand: the chips and who can win them."""
        live = [p for p in state.in_hand if p not in state.folded]
        if len(live) < 2 or not state.contributions:
            return []
        pots = side_pots(dict(state.contributions), list(state.folded))
        return [{"amount": pot.amount, "eligible": list(pot.eligible)} for pot in pots]

    def _win_chances(self, state: PokerState) -> dict[PlayerId, float]:
        """Each player's chance to win if the hand ran to the river now, for the spectator view.

        Spectator information only (it follows from every hole card). The random
        runouts use a stream fixed by the hand and the board, so the same state
        always gives the same numbers.
        """
        live = [p for p in state.in_hand if p not in state.folded and state.hole.get(p)]
        if len(live) < 2:
            return {}
        holes = {p: [Card.parse(c) for c in state.hole[p]] for p in live}
        board = [Card.parse(c) for c in state.board]
        rng = random.Random(f"win-chances/{state.hand_no}/{len(board)}")
        return win_probabilities(holes, board, rng, samples=400)

    # --- end ---------------------------------------------------------------

    def is_over(self, state: PokerState) -> bool:
        return state.phase == "over"

    def results(self, state: PokerState) -> list[Placement]:
        """Players still holding chips by stack, then the eliminated in reverse order.

        Among players knocked out in the same hand, more chips at its start ranks
        higher. Equal stacks (or equal starting chips) share a rank.
        """
        alive = [(p, state.stacks[p]) for p in state.seats if state.stacks[p] > 0]
        groups = [alive] + [list(group) for group in reversed(state.eliminated)]
        placements: list[Placement] = []
        rank = 1
        for group in groups:
            ordered = sorted(group, key=lambda entry: -entry[1])
            for index, (player, chips) in enumerate(ordered):
                if index and chips == ordered[index - 1][1]:
                    shared = placements[-1].rank
                else:
                    shared = rank + index
                placements.append(Placement(player=player, rank=shared))
            rank += len(ordered)
        return placements

    def random_action(
        self, observation: Mapping[str, Any], tools: Sequence[ToolSpec], rng: random.Random
    ) -> Action:
        names = {tool.name for tool in tools}
        roll = rng.random()
        if "raise" in names and roll < 0.18:
            low, high = observation["min_raise_to"], observation["max_raise_to"]
            return Action(tool="raise", arguments={"amount": rng.randint(low, min(high, low * 3))})
        if "all_in" in names and roll < 0.22:
            return Action(tool="all_in")
        if "check" in names:
            return Action(tool="check")
        if roll < 0.45:
            return Action(tool="fold")
        return Action(tool="call")

    # --- helpers -----------------------------------------------------------

    def _position(self, state: PokerState, player: PlayerId) -> str | None:
        if player not in state.in_hand or state.button is None:
            return None
        if player == state.button:
            return "button"
        order = self._from(state.in_hand, state.button)
        heads_up = len(order) == 2
        if heads_up:
            return "big_blind"
        return {1: "small_blind", 2: "big_blind"}.get(
            order.index(player), f"seat_{order.index(player)}"
        )

    @staticmethod
    def _from(players: Sequence[PlayerId], first: PlayerId) -> list[PlayerId]:
        index = players.index(first)
        return list(players[index:]) + list(players[:index])

    @staticmethod
    def _next_in(
        seats: Sequence[PlayerId], seated: Sequence[PlayerId], after: PlayerId
    ) -> PlayerId:
        index = seats.index(after)
        for offset in range(1, len(seats) + 1):
            candidate = seats[(index + offset) % len(seats)]
            if candidate in seated:
                return candidate
        raise AssertionError("nobody left to hold the button")
