# D-052 · A finished API match rates its random bots

- **Date:** 2026-11-11
- **Decision:** When a match started through `POST /matches` finishes,
  `LiveMatches` (`arena/api/live.py`) applies its placements to the ratings
  (`RatingStore.apply_match_result`, keyed by the match id, so it counts once).
  Every seat has a bot profile, "Random Bot p1", "Random Bot p2", ...
  (`model_id` `random-bot`), created on first use with an id derived from the
  seat name. Failed, interrupted and paused matches are not rated. A rating
  error is logged and never fails the match. `demo_seed` ignores `random-bot`
  profiles when it checks for real profiles. The `arena` command stores
  nothing, so it rates nothing.
- **Why:** A profile can be rated only once per match, so the bots need one
  profile per seat, not one per kind. The leaderboard then fills from real
  matches. Rating after the record is closed keeps the match status true even
  if the rating fails.
- **Alternatives:** one profile per bot kind (impossible: the same profile
  twice in one match); rating only matches with real model players (the
  leaderboard would stay empty until phase 2).
