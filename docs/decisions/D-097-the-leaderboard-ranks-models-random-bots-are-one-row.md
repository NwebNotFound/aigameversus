# D-097 · The leaderboard ranks models; random bots are one row

- **Date:** 2026-11-11
- **Decision:** `GET /leaderboard` takes `kind=models|bots|all`. Without it, real
  models are shown, or everyone when no model is rated yet (`fallback: true`);
  `counts` gives the rows per kind. The per-seat profiles of random bots ("Random
  Bot p3", D-052) are grouped into one "Random Bot" row with their ratings,
  win rates and placements averaged by games played (`members` says how many
  seats); `group_bots=false` lists every seat, for tests and the profile pages.
  Each row also has the vendor (from `config/models.yaml`), the average cost of
  one rated game (the ledger's booked calls of the profile's seats over its
  rated games) and the tool-error rate: refused answers over all answers
  (`action_rejected` / (`action_accepted` + `action_rejected`) of its seats).
  The web page filters by kind and keeps the game tab.
- **Why:** The board compares models; a bot has no identity beyond its kind, and
  a per-kind profile cannot hold several seats of one match (a profile is rated
  once per match), so the grouping is done where the board is read.
- **Alternatives:** one stored profile per bot kind (impossible with several bot
  seats per match); hiding bots altogether (the demo needs them).
