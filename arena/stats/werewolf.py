"""Werewolf statistics: pure functions over the event log of one match.

Input is the whole stored log as a spectator sees it (roles included).
These numbers use hidden information: they must never reach a player's prompt or
memory while a match is running (roadmap 6.3).
Definitions, per player:

- **Rounds**: a round is a night and the day after it, numbered by
  `night_started`. A player who dies in round `n` (at night or by the vote of
  day `n`) was alive for `rounds_alive = n` rounds; a survivor was alive for all
  rounds of the match.
- **Vote accuracy**: of the votes a player cast for someone (abstaining does not
  count) while not on the wolf side, the share that went to a wolf. The wolf
  side is the pack of `pack_revealed` plus players who later join it
  (`joined_pack`, `infected`). Votes of wolves are left out: for them hitting a
  wolf is not the goal. The captain election is not a vote in this sense.
- **Seer outing speed**: for the player whose role was the seer, how many rounds
  they lived (`rounds_alive`) and whether they died. A seer who is found and
  killed early lives few rounds.
- **Won**: the player is in the `winners` of `game_over`.
"""

from collections.abc import Iterable, Sequence

from pydantic import BaseModel

from arena.engine.types import Event, PlayerId
from arena.ratings.stats import rate

SEER = "seer"


class WerewolfMatchStats(BaseModel):
    """What one player did in one match."""

    player: PlayerId
    role: str | None = None
    won: bool = False
    died: bool = False
    death_cause: str | None = None
    rounds_alive: int = 0
    votes_for_wolves: int = 0
    votes_for_villagers: int = 0
    abstentions: int = 0


class WerewolfTotals(BaseModel):
    """Many matches of one player added up. `None` means no data, not 0."""

    matches: int
    wins: int
    deaths: int
    votes_for_wolves: int
    votes_for_villagers: int
    abstentions: int
    vote_accuracy: float | None
    win_rate: float | None
    rounds_alive_per_match: float | None
    seer_matches: int
    seer_deaths: int
    seer_rounds_alive_per_match: float | None


def match_stats(events: Iterable[Event]) -> dict[PlayerId, WerewolfMatchStats]:
    """The statistics of every player of a finished (or partial) Werewolf log."""
    events = list(events)
    start = next((e for e in events if e.type == "match_started"), None)
    if start is None or start.data["game"] != "werewolf":
        raise ValueError("not the log of a Werewolf match")
    stats = {p: WerewolfMatchStats(player=p) for p in start.data["players"]}
    wolves: set[PlayerId] = set()
    round_no = 0

    for event in events:
        data = event.data
        match event.type:
            case "role_assigned":
                stats[data["player"]].role = data["role"]
            case "pack_revealed":
                wolves |= set(data["wolves"])
            case "joined_pack" | "infected":
                wolves.add(data["player"])
            case "night_started":
                round_no = data["night"]
            case "vote_cast":
                _vote(stats, wolves, data)
            case "player_died":
                me = stats[data["player"]]
                me.died, me.death_cause, me.rounds_alive = True, data["cause"], round_no
            case "game_over":
                for player in data["winners"]:
                    stats[player].won = True
    for me in stats.values():
        if not me.died:
            me.rounds_alive = round_no
    return stats


def _vote(stats: dict[PlayerId, WerewolfMatchStats], wolves: set[PlayerId], data: dict) -> None:
    me, target = stats[data["player"]], data["target"]
    if target is None:
        me.abstentions += 1
    elif me.player not in wolves:
        if target in wolves:
            me.votes_for_wolves += 1
        else:
            me.votes_for_villagers += 1


def aggregate(matches: Sequence[WerewolfMatchStats]) -> WerewolfTotals:
    """One player's statistics over many matches (one entry per match)."""
    seers = [m for m in matches if m.role == SEER]
    for_wolves = sum(m.votes_for_wolves for m in matches)
    for_villagers = sum(m.votes_for_villagers for m in matches)
    wins = sum(m.won for m in matches)
    return WerewolfTotals(
        matches=len(matches),
        wins=wins,
        deaths=sum(m.died for m in matches),
        votes_for_wolves=for_wolves,
        votes_for_villagers=for_villagers,
        abstentions=sum(m.abstentions for m in matches),
        vote_accuracy=rate(for_wolves, for_wolves + for_villagers),
        win_rate=rate(wins, len(matches)),
        rounds_alive_per_match=_mean([m.rounds_alive for m in matches]),
        seer_matches=len(seers),
        seer_deaths=sum(m.died for m in seers),
        seer_rounds_alive_per_match=_mean([m.rounds_alive for m in seers]),
    )


def _mean(values: Sequence[int]) -> float | None:
    return None if not values else sum(values) / len(values)
