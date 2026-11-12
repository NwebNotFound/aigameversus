# D-081 · A model has one rating profile, whatever seat it sits in

- **Date:** 2026-11-11
- **Decision:** A finished model match is rated, whether it was started with
  `arena run --models` or with `POST /matches` (final rule; D-082 once left the
  API unrated as a step). Each model gets
  one profile per personality (`RatingStore.model_profile`; the id derives from
  model id and personality, so it is the same in every match and every seat; no
  personality is chosen from the command line yet). Its rating, statistics and
  cost therefore add up across matches. A profile is rated once per match, so a
  match with the same model in several seats is left unrated and the command says
  so. Random bots keep one profile per seat, as the log needs a seat per profile
  (D-052); the leaderboard groups them by kind when it shows them.
  The API rates a finished match in its own task: once per match id, a rating
  problem is logged and never fails the match. `arena ratings backfill` rates
  the finished model matches that were played before (also imported ones), and
  can be run again. Demo profiles (`arena.ratings.demo_seed`) carry
  `is_demo`; the leaderboard leaves them out unless asked (`demo=true`, the
  "Show demo data" switch), and says how many it hides.
- **Why:** The leaderboard compares models, not seats: a model that sat in seat 3
  yesterday and seat 1 today is the same player. Rating the same profile twice in
  one match would break the match's placements.
- **Alternatives:** rating the model's best seat, or splitting its placements
  (arbitrary); one profile per model and seat (the old way: no comparison).
