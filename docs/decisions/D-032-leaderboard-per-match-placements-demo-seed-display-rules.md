# D-032 · Leaderboard: per-match placements, demo seed, display rules

- **Date:** 2026-11-11
- **Decision:** A new table `match_placements` (migration 0003) keeps each rated
  player's rank, table size and rating before and after, per match. Win rate
  (share of matches at rank 1), average placement and a profile's recent
  matches come from it. `GET /leaderboard?game=<id>` returns rows sorted by
  rating, then name; without `game` it uses the overall rating (D-031) and sums
  games, wins and placements over all games. The row `rank` is the position on
  the board. Ratings and changes are rounded to one decimal in API answers and
  to whole numbers in the UI. Profiles without a rated match are left off the
  board. Relations and memory on a profile are explicit "not available yet"
  placeholders until phase 6. `python -m arena.ratings.demo_seed` fills the
  tables with six "DEMO …" profiles (model `random-bot`, fixed ids) playing
  real High Card matches as random bots, with match ids derived from the seed:
  re-running adds nothing, and it refuses when any non-demo profile exists.
  CI seeds its fresh database for the leaderboard Playwright tests.
- **Why:** Win rate and placement cannot be derived from the rating rows alone,
  and storing them per match also gives match history. Demo data from real
  bot matches exercises the same write path as real results, at no cost.
- **Alternatives:** counters on `ratings` (no history); computing stats from
  the event logs on each request; a static JSON fixture for the UI.
