# D-054 · Poker statistics: definitions

- **Date:** 2026-11-11
- **Decision:** `arena/stats/poker.py` counts, over the hands a player was
  dealt into: VPIP (a call, raise or all-in before the flop; blinds and a free
  check do not count), aggression factor (aggressive actions / calls; an
  all-in is aggressive only if it goes above the street's highest bet), bluff
  rate (bluff hands / hands with a bet or raise; a bluff hand is a win without
  showdown with less than a pair, or a showdown loss), chips per 100 hands
  (pot shares won minus chips put in, blinds included) and worst decisions
  (a fold whose cards plus the final board would have beaten every shown hand
  at the showdown).
- **Why:** The spec names the numbers but not the formulas. These use only
  events the plugin already emits, including the spectator-only hole cards,
  and chips balance exactly (the net chips of all players sum to 0, which the
  tests check on real bot matches).
- **Alternatives:** counting a showdown loss only when the hand was weak
  (needs a notion of a "strong" hand); counting every all-in as aggressive.
