# D-063 · Profile statistics: seats stored at rating time, totals read from the logs

- **Date:** 2026-11-11
- **Decision:**
  - The rating of a match also stores which seat of its log each profile
    played (`match_seats`, migration `0007`), in the same transaction as the
    ratings. Matches rated without seats (the DEMO seed) have no statistics.
  - `GET /profiles/{id}/stats?game=` loads the log of every rated match of the
    profile in that game, runs the game's `match_stats` from `arena/stats` and
    returns its `aggregate` per game. Nothing is cached: the logs are the truth
    and the statistics follow any fix of a stats module at once. Without
    `game`, every game with statistics the profile played; a game without
    statistics answers 404.
  - At most the newest 200 rated matches per game count (`MAX_STATS_MATCHES`);
    `matches` says how many did.
  - The profile page shows one table per game, the fields of the game's totals
    in their order, shares as percent.
- **Why:** The seat is the only link between a profile and its events; storing
  it when the match is rated keeps one place that knows both. Computing on
  request is fast enough for today's match counts, and the cap bounds a
  random-bot profile, which sits in every bot match.
- **Alternatives:** stored totals per profile and game (to be added when a
  profile has thousands of matches); seats in `match_placements`.
