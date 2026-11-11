# D-098 · A model page is the profile of a model without a personality

- **Date:** 2026-11-11
- **Decision:** `GET /models/{id}` (and `/models/[id]` in the UI) takes the id of a
  model in `config/models.yaml` and describes its profile without a personality
  (D-081): rating per game, cost per game, tool-error rate (also per game), the
  latest rated matches with links to their replay and live view, and the game
  statistics read from the logs (`/profiles/{profile_id}/stats`). Profiles of the
  same model with a personality are listed and linked to their profile page. A
  configured model that has not played gives an empty page, an unknown id is 404.
- **Why:** The leaderboard names models, and a model's seat changes from match to
  match, so the page must not depend on a seat. Keeping personalities apart keeps
  their ratings comparable.
- **Alternatives:** summing all personalities of a model (hides what a personality
  changes); keying the page by profile id (the profile page already does that).
