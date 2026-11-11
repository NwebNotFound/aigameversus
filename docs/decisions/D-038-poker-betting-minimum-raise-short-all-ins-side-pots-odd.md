# D-038 · Poker betting: minimum raise, short all-ins, side pots, odd chips

- **Date:** 2026-11-11
- **Decision:** `games/poker/betting.py` implements No-Limit betting rules as
  pure code. `raise(amount)` names the total bet for the round ("raise to").
  The minimum raise is the current bet plus the size of the last full raise,
  and at least the big blind; before the flop that is double the big blind, as
  the spec's "double the last bet". An all-in below a full raise does not
  reopen raising for players who already acted: they may only call or fold,
  and going all-in is refused for them when it would put in more than a call.
  A big blind posted short does not lower the bet: the others still owe the
  full big blind (the short blind is all-in, side pots sort out the rest).
  Side pots come from each player's total contribution in the hand; folded
  chips stay in the pots, and a pot that only one player can win returns an
  uncalled bet. Odd chips of a split pot go one each to the winners in seat
  order starting left of the button.
- **Why:** These are the standard tournament rules; they keep every chip
  accounted for and are what poker players and models expect.
- **Alternatives:** the spec's literal "double the last bet" for every raise;
  odd chips to the best hand by suit; letting short all-ins reopen raising.
