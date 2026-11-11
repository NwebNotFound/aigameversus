"""Poker statistics: pure functions over the event log of one match.

Input is the whole stored log as a spectator sees it (hole cards included).
Definitions, per player, counted over the hands the player was dealt into:

- **VPIP**: hands in which the player voluntarily put chips in before the flop
  (a call, a raise or an all-in; blinds and a free check do not count).
- **Aggression factor**: aggressive actions / calls, over all streets. A raise
  is aggressive; an all-in is aggressive if it goes above the highest bet of the
  street so far, else it is a call. `None` without calls.
- **Bluff rate**: bluff hands / hands with an aggressive action. A bluff hand is
  one where the player bet or raised and then either won without a showdown
  holding less than a pair (judged on the hole cards and the board dealt so far;
  with fewer than five cards known, on the hole cards alone), or lost at the
  showdown. A raise followed by a fold, or a win with a pair or better, is not
  a bluff.
- **Chips per 100 hands**: (chips won from pots - chips put in, blinds
  included) / hands * 100.
- **Worst decisions**: hands that reached a showdown in which the player had
  folded, but whose cards plus the final board would have beaten every hand
  shown at the showdown.
"""

from collections.abc import Iterable, Sequence

from pydantic import BaseModel

from arena.engine.types import Event, PlayerId
from arena.ratings.stats import rate
from games.poker.cards import Card
from games.poker.evaluator import HandCategory, best_hand


class PokerMatchStats(BaseModel):
    """What one player did in one match."""

    player: PlayerId
    hands: int = 0
    vpip_hands: int = 0
    aggressive_actions: int = 0
    calls: int = 0
    aggressive_hands: int = 0
    bluff_hands: int = 0
    net_chips: int = 0
    worst_decisions: int = 0


class PokerTotals(BaseModel):
    """Many matches of one player added up. `None` means no data, not 0."""

    matches: int
    hands: int
    vpip_hands: int
    aggressive_actions: int
    calls: int
    aggressive_hands: int
    bluff_hands: int
    net_chips: int
    worst_decisions: int
    vpip: float | None
    aggression_factor: float | None  # aggressive actions per call; can exceed 1
    bluff_rate: float | None
    chips_per_100_hands: float | None


class _Hand:
    """What the log says about the hand being read."""

    def __init__(self, players: list[PlayerId], big_blind: int):
        self.players = players
        self.hole: dict[PlayerId, list[str]] = {}
        self.board: list[str] = []
        self.invested = dict.fromkeys(players, 0)
        self.won = dict.fromkeys(players, 0)
        self.folded: set[PlayerId] = set()
        self.vpip: set[PlayerId] = set()
        self.aggressive: set[PlayerId] = set()
        self.shown: list[dict] = []
        self.street_high = big_blind  # highest bet on the current street so far


def match_stats(events: Iterable[Event]) -> dict[PlayerId, PokerMatchStats]:
    """The statistics of every player of a finished (or partial) Poker log."""
    events = list(events)
    start = next((e for e in events if e.type == "match_started"), None)
    if start is None or start.data["game"] != "poker":
        raise ValueError("not the log of a Poker match")
    stats = {p: PokerMatchStats(player=p) for p in start.data["players"]}
    hand: _Hand | None = None

    for event in events:
        data = event.data
        if event.type == "hand_started":
            hand = _Hand(list(data["players"]), data["big_blind"])
        elif hand is None:
            continue
        elif event.type == "hole_dealt":
            hand.hole[data["player"]] = list(data["cards"])
        elif event.type == "blind_posted":
            hand.invested[data["player"]] += data["amount"]
        elif event.type == "street_started":
            hand.board += data["cards"]
            hand.street_high = 0
        elif event.type == "bet_action":
            _bet(hand, stats[data["player"]], data)
        elif event.type == "showdown":
            hand.shown = list(data["hands"])
        elif event.type == "pot_awarded":
            for player, amount in data["shares"].items():
                hand.won[player] += amount
        elif event.type == "hand_ended":
            _finish(hand, stats)
            hand = None
    return stats


def _bet(hand: _Hand, me: PokerMatchStats, data: dict) -> None:
    player, kind, to = data["player"], data["kind"], data["to"]
    hand.invested[player] += data["added"]
    if kind == "fold":
        hand.folded.add(player)
        return
    if kind == "check":
        return
    raised = kind == "raise" or (kind == "all_in" and to > hand.street_high)
    hand.street_high = max(hand.street_high, to)
    if raised:
        me.aggressive_actions += 1
        hand.aggressive.add(player)
    else:
        me.calls += 1
    if data["street"] == "preflop":
        hand.vpip.add(player)


def _finish(hand: _Hand, stats: dict[PlayerId, PokerMatchStats]) -> None:
    showdown_values = [
        best_hand([*map(Card.parse, h["cards"]), *map(Card.parse, hand.board)]) for h in hand.shown
    ]
    shown_players = {h["player"] for h in hand.shown}
    for player in hand.players:
        me = stats[player]
        me.hands += 1
        me.net_chips += hand.won[player] - hand.invested[player]
        me.vpip_hands += player in hand.vpip
        if player in hand.aggressive:
            me.aggressive_hands += 1
            lost_showdown = player in shown_players and hand.won[player] == 0
            won_weak = (
                not hand.shown
                and hand.won[player] > 0
                and _weaker_than_a_pair(hand.hole.get(player, []), hand.board)
            )
            me.bluff_hands += lost_showdown or won_weak
        if showdown_values and player in hand.folded and player in hand.hole:
            full = [*map(Card.parse, hand.hole[player]), *map(Card.parse, hand.board)]
            me.worst_decisions += best_hand(full) > max(showdown_values)


def _weaker_than_a_pair(hole: Sequence[str], board: Sequence[str]) -> bool:
    cards = [*map(Card.parse, hole), *map(Card.parse, board)]
    if len(cards) >= 5:
        return best_hand(cards).category < HandCategory.ONE_PAIR
    return len({card.rank for card in cards}) == len(cards)  # fewer than 5 known: no pair


def aggregate(matches: Sequence[PokerMatchStats]) -> PokerTotals:
    """One player's statistics over many matches (one entry per match)."""

    def total(field: str) -> int:
        return sum(getattr(m, field) for m in matches)

    hands = total("hands")
    return PokerTotals(
        matches=len(matches),
        hands=hands,
        vpip_hands=total("vpip_hands"),
        aggressive_actions=total("aggressive_actions"),
        calls=total("calls"),
        aggressive_hands=total("aggressive_hands"),
        bluff_hands=total("bluff_hands"),
        net_chips=total("net_chips"),
        worst_decisions=total("worst_decisions"),
        vpip=rate(total("vpip_hands"), hands),
        aggression_factor=None
        if not total("calls")
        else total("aggressive_actions") / total("calls"),
        bluff_rate=rate(total("bluff_hands"), total("aggressive_hands")),
        chips_per_100_hands=None if not hands else total("net_chips") / hands * 100,
    )
