# D-031 · Multiplayer Elo, the overall rating, and rating storage

- **Date:** 2026-11-11
- **Decision:** A match counts as every pairwise duel between its players
  (ahead = win, same rank = draw) with the classic expectation
  `1 / (1 + 10^((opponent − own) / 400))`. A player's change is
  `K / (n − 1) × Σ (score − expected)`, with K = 32 by default, so the winner of
  a 6-player match among equals gains as much as the winner of a duel (+16).
  Deltas of a match sum to zero. Ratings are floats, rounded only for display.
  Everyone starts at 1000 per game. The overall rating is the mean of a
  player's per-game ratings weighted by games played (1000 with no games).
  Storage: `player_profiles`, `ratings` (one row per profile and game) and
  `rated_matches`. Applying a match first claims its id in `rated_matches`, so
  the same match never counts twice, and does everything in one transaction
  with rows locked in profile-id order. The migration is forward-only like all
  others (D-014), so there is no down step.
- **Why:** Normalising by opponents keeps ratings comparable across games with
  2 to 16 players. Weighting by games played stops one lucky game in a rarely
  played title from moving the overall rating as much as fifty poker matches.
- **Alternatives:** unnormalised pairwise K (big tables swing ratings n − 1
  times as hard); TrueSkill or Glicko (better uncertainty, harder to explain);
  a plain mean or the maximum of per-game ratings for the overall value.
