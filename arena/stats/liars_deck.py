"""Liar's Deck statistics: pure functions over the event log of one match.

Input is the whole stored log, as a spectator sees it (private events included:
`cards_hidden` shows what a player really played). Nothing here changes a plugin.

Definitions, per player:

- **plays**: `play_cards` turns. **lies**: plays with a card that is neither the
  round's table card nor a joker. Lie rate = lies / plays.
- **times caught**: reveals of the player's cards that were not honest
  (a call on a lie, also an automatic one).
- **calls**: "Liar!" calls the player chose to make (automatic calls are forced
  and left out). A call is **correct** if the revealed play was not honest.
- **rounds played**: rounds that started with the player alive. **eliminated**:
  a live trigger pull.
- **boldest bluff**: the highest revolver risk the player faced while telling a
  lie: live chambers left / chambers left, at the time of the play (0 to 1).
"""

from collections.abc import Iterable, Sequence

from pydantic import BaseModel

from arena.engine.types import Event, EventSource, PlayerId
from arena.ratings.stats import bluff_rate, rate
from games.liars_deck.plugin import JOKER, card_rank
from games.liars_deck.variants import load_variants


class LiarsDeckMatchStats(BaseModel):
    """What one player did in one match."""

    player: PlayerId
    plays: int = 0
    lies: int = 0
    times_caught: int = 0
    calls: int = 0
    calls_correct: int = 0
    rounds_played: int = 0
    eliminated: bool = False
    boldest_bluff_risk: float | None = None


class LiarsDeckTotals(BaseModel):
    """Many matches of one player added up. Rates are shares from 0 to 1, `None` without data."""

    matches: int
    plays: int
    lies: int
    times_caught: int
    calls: int
    calls_correct: int
    rounds_played: int
    eliminations: int
    lie_rate: float | None
    caught_share: float | None  # times caught / lies
    call_success_rate: float | None
    rounds_survived_per_match: float | None
    boldest_bluff_risk: float | None


def match_stats(events: Iterable[Event]) -> dict[PlayerId, LiarsDeckMatchStats]:
    """The statistics of every player of a finished (or partial) Liar's Deck log."""
    events = list(events)
    start = next((e for e in events if e.type == "match_started"), None)
    if start is None or start.data["game"] != "liars_deck":
        raise ValueError("not the log of a Liar's Deck match")
    variant = load_variants()[start.data["settings"].get("variant", "base")]
    stats = {p: LiarsDeckMatchStats(player=p) for p in start.data["players"]}
    live_chambers: dict[PlayerId, int] = {}
    pulls = dict.fromkeys(stats, 0)
    table_card = ""
    chosen_caller: PlayerId | None = None  # who made the call that is being resolved

    for event in (e for e in events if e.source is EventSource.GAME):
        data = event.data
        match event.type:
            case "revolver_loaded":
                live_chambers[data["player"]] = len(data["live"])
            case "round_started":
                table_card = data["table_card"]
                for player in data["players"]:
                    stats[player].rounds_played += 1
            case "cards_hidden":
                me = stats[data["player"]]
                me.plays += 1
                if any(card_rank(card) not in (table_card, JOKER) for card in data["cards"]):
                    me.lies += 1
                    left = variant.revolver.chambers - pulls[data["player"]]
                    risk = live_chambers[data["player"]] / left
                    me.boldest_bluff_risk = max(me.boldest_bluff_risk or 0.0, risk)
            case "liar_called":
                chosen_caller = None if data["automatic"] else data["caller"]
                if chosen_caller:
                    stats[chosen_caller].calls += 1
            case "cards_revealed":
                if not data["honest"]:
                    stats[data["player"]].times_caught += 1
                    if chosen_caller:
                        stats[chosen_caller].calls_correct += 1
            case "trigger_pulled":
                pulls[data["player"]] += 1
                if data["live"]:
                    stats[data["player"]].eliminated = True
    return stats


def aggregate(matches: Sequence[LiarsDeckMatchStats]) -> LiarsDeckTotals:
    """One player's statistics over many matches (one entry per match)."""
    total = lambda field: sum(getattr(m, field) for m in matches)  # noqa: E731
    risks = [m.boldest_bluff_risk for m in matches if m.boldest_bluff_risk is not None]
    eliminations = sum(m.eliminated for m in matches)
    # Rounds survived: every round played, except the one in which the player fell.
    survived = total("rounds_played") - eliminations
    return LiarsDeckTotals(
        matches=len(matches),
        plays=total("plays"),
        lies=total("lies"),
        times_caught=total("times_caught"),
        calls=total("calls"),
        calls_correct=total("calls_correct"),
        rounds_played=total("rounds_played"),
        eliminations=eliminations,
        lie_rate=bluff_rate(total("lies"), total("plays")),
        caught_share=rate(total("times_caught"), total("lies")),
        call_success_rate=rate(total("calls_correct"), total("calls")),
        rounds_survived_per_match=None if not matches else survived / len(matches),
        boldest_bluff_risk=max(risks, default=None),
    )
