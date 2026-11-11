"""No-Limit betting: one betting round, side pots and splitting a pot. No cards, no I/O.

A `Street` is one betting round (preflop, flop, turn or river). The plugin
keeps it in its state and changes it only by applying actions:

    street = Street.open(order, stacks, big_blind=20, posted={"sb": 10, "bb": 20})
    street.legal("p3")                 # what p3 may do now
    street.apply("p3", "raise", 60)    # raise to 60 in total this round
    street.next_actor()                # who acts next, or None when the round is over

Amounts in `apply` are the player's *total* bet in this round ("raise to").
Chips never appear or vanish: every chip a player bets leaves their stack.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel

Kind = Literal["fold", "check", "call", "raise", "all_in"]


@dataclass(frozen=True)
class Legal:
    """What one player may do now. The raise bounds are None when raising is not allowed."""

    can_check: bool
    call_amount: int  # chips to add to call; 0 when checking is possible
    min_raise_to: int | None
    max_raise_to: int | None  # all chips: stack plus what is already bet this round


@dataclass(frozen=True)
class Pot:
    amount: int
    eligible: tuple[str, ...]  # players who can win it, in seat order


class Street(BaseModel):
    order: list[str]  # players in this hand, in acting order for this round
    stacks: dict[str, int]  # chips behind, not yet bet
    bets: dict[str, int]  # chips bet in this round
    folded: list[str] = []
    all_in: list[str] = []
    current_bet: int = 0
    last_raise: int  # size of the last full raise; the next raise must be at least this
    to_act: list[str]  # players who still have to act, in order
    may_raise: list[str]  # players allowed to raise when they act

    @classmethod
    def open(
        cls,
        order: Sequence[str],
        stacks: Mapping[str, int],
        *,
        big_blind: int,
        posted: Mapping[str, int] | None = None,
        folded: Sequence[str] = (),
        all_in: Sequence[str] = (),
    ) -> "Street":
        """A new betting round. `posted` are forced bets (blinds) already in front of players.

        `stacks` are the chips behind after those bets. Players already all-in or
        folded take no part in the betting.
        """
        posted = dict(posted or {})
        bets = {p: posted.get(p, 0) for p in order}
        all_in = [p for p in order if p in all_in or (stacks[p] == 0 and p not in folded)]
        active = [p for p in order if p not in folded and p not in all_in]
        current = max(bets.values(), default=0)
        if posted:  # a short big blind does not lower what the others must call
            current = max(current, big_blind)
        street = cls(
            order=list(order),
            stacks={p: stacks[p] for p in order},
            bets=bets,
            folded=list(folded),
            all_in=all_in,
            current_bet=current,
            last_raise=big_blind,
            to_act=active,
            may_raise=list(active),
        )
        # With fewer than two players able to bet and nobody facing a bet, there is no round.
        if len(active) < 2 and all(bets[p] >= current for p in active):
            street.to_act = []
        return street

    # --- queries -----------------------------------------------------------

    def next_actor(self) -> str | None:
        return self.to_act[0] if self.to_act else None

    def live(self) -> list[str]:
        """Players still in the hand (not folded), in order."""
        return [p for p in self.order if p not in self.folded]

    def legal(self, player: str) -> Legal:
        owed = self.current_bet - self.bets[player]
        stack = self.stacks[player]
        call = min(owed, stack)
        total = self.bets[player] + stack
        can_raise = player in self.may_raise and total > self.current_bet
        min_to = self.current_bet + self.last_raise
        return Legal(
            can_check=owed <= 0,
            call_amount=max(call, 0),
            min_raise_to=min(min_to, total) if can_raise else None,
            max_raise_to=total if can_raise else None,
        )

    def problem(self, player: str, kind: Kind, amount: int | None = None) -> str | None:
        """Why this action is not allowed now, or None if it is."""
        if player != self.next_actor():
            return f"It is not your turn; {self.next_actor()} acts now."
        legal = self.legal(player)
        if kind == "check" and not legal.can_check:
            return f"You cannot check: {legal.call_amount} to call. Call, raise or fold."
        if kind == "call" and legal.can_check:
            return "There is nothing to call; check instead."
        all_chips = self.bets[player] + self.stacks[player]
        if kind == "all_in" and legal.min_raise_to is None and all_chips > self.current_bet:
            return "You may not raise now, and all your chips would be a raise; call or fold."
        if kind == "raise":
            if legal.min_raise_to is None:
                return "You may not raise now; call or fold."
            if amount is None:
                return "Say the total you raise to, as `amount`."
            if amount > legal.max_raise_to:
                return f"You have only {legal.max_raise_to} chips in total; raise to at most that."
            if amount < legal.min_raise_to:
                return (
                    f"The minimum raise is to {legal.min_raise_to} "
                    f"(the bet of {self.current_bet} plus the last raise of {self.last_raise})."
                )
        return None

    # --- changes -----------------------------------------------------------

    def apply(self, player: str, kind: Kind, amount: int | None = None) -> int:
        """Apply a legal action; return the chips the player added. Check with `problem` first."""
        before = self.bets[player]
        if kind == "fold":
            self.folded.append(player)
            self._done(player)
            return 0
        if kind == "check":
            self._done(player)
            return 0
        if kind == "call":
            target = min(self.current_bet, before + self.stacks[player])
        elif kind == "all_in":
            target = before + self.stacks[player]
        else:
            target = amount
        added = target - before
        self.stacks[player] -= added
        self.bets[player] = target
        if self.stacks[player] == 0:
            self.all_in.append(player)
        if target > self.current_bet:
            raise_size = target - self.current_bet
            full = raise_size >= self.last_raise
            self.current_bet = target
            self._reopen(player, full)
            if full:
                self.last_raise = raise_size
        else:
            self._done(player)
        return added

    def _done(self, player: str) -> None:
        if player in self.to_act:
            self.to_act.remove(player)
        if player in self.may_raise:
            self.may_raise.remove(player)
        if len([p for p in self.live() if p not in self.all_in]) <= 1:
            # Nobody left to bet against: only a player facing a bet still acts.
            self.to_act = [p for p in self.to_act if self.bets[p] < self.current_bet]

    def _reopen(self, raiser: str, full: bool) -> None:
        """After a bet or raise, everyone else who can act must act again, after the raiser.

        Only a full raise lets players who already acted raise again; a short
        all-in only makes them call or fold.
        """
        index = self.order.index(raiser)
        after = self.order[index + 1 :] + self.order[:index]
        able = [p for p in after if p not in self.folded and p not in self.all_in]
        self.to_act = able
        if full:
            self.may_raise = list(able)
        else:
            self.may_raise = [p for p in self.may_raise if p in able]
        if raiser in self.may_raise:
            self.may_raise.remove(raiser)


def side_pots(contributions: Mapping[str, int], folded: Sequence[str]) -> list[Pot]:
    """Split a hand's chips into the main pot and side pots.

    `contributions` are the chips each player put in during the whole hand, in
    seat order. Folded players' chips go into the pots but they cannot win. A
    pot only one player can win returns an uncalled bet to that player.
    """
    folded_set = set(folded)
    live_levels = sorted({c for p, c in contributions.items() if c > 0 and p not in folded_set})
    pots: list[Pot] = []
    previous = 0
    for level in live_levels:
        amount = sum(min(c, level) - min(c, previous) for c in contributions.values())
        eligible = tuple(p for p, c in contributions.items() if p not in folded_set and c >= level)
        if pots and pots[-1].eligible == eligible:
            pots[-1] = Pot(pots[-1].amount + amount, eligible)
        else:
            pots.append(Pot(amount, eligible))
        previous = level
    # Folded players may have put in more than any live player: that goes to the last pot.
    leftover = sum(max(0, c - previous) for c in contributions.values())
    if leftover:
        if not pots:
            raise ValueError("chips in the pot but nobody left to win them")
        pots[-1] = Pot(pots[-1].amount + leftover, pots[-1].eligible)
    return pots


def split(amount: int, winners: Sequence[str]) -> dict[str, int]:
    """Share a pot evenly; odd chips go one each to the first winners in the given order.

    The plugin passes winners in seat order starting left of the button, the
    usual rule for odd chips (D-034).
    """
    if not winners:
        raise ValueError("a pot needs at least one winner")
    share, odd = divmod(amount, len(winners))
    return {player: share + (1 if index < odd else 0) for index, player in enumerate(winners)}
