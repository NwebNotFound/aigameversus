# D-137 · Proposed: domination counts only once the world has two cities per nation

- **Date:** 2026-11-12
- **Status:** accepted by the lead on 2026-11-12, in force from Throne of Tokens
  version 2 (`CivGame.version`, recorded in `match_started`).
- **Decision:** A domination victory is checked only when the world holds at
  least two cities per nation (8 for four nations), as a number in
  `victory.yaml`: `domination.min_cities_per_nation: 2`. Nothing else changes.
- **Why:** In the bot sweep, 10 of 80 four-nation matches of 60 rounds end by
  domination, 9 of them by round 26 and the earliest in round 7. Early on few
  cities exist: a nation that settles twice holds 3 of 6 cities, half the world
  and more than anyone, and wins without a single battle. DESIGN.md means
  domination as control of the world, not as the fastest second settler. With
  the minimum (tried in memory on the same 80 seeds) the wins before round 18 are
  gone; 7 dominations remain, from round 18 on. Five and six nations never
  reach domination in the sweep either way.
- **Alternatives:** Domination only after a round, such as 15 (a second number
  and a hard edge); only with at least one conquered city (closer to the
  spec's idea, but random bots never attack, so the sweep cannot measure it);
  leave it (a model that sees the scoreboard can race for it in a 4-nation
  match).
