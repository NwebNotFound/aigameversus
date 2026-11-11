# D-082 · Model seats in POST /matches, off by default and confirmed per match

- **Date:** 2026-11-11
- **Decision:** `POST /matches` takes `models` (model ids, one per seat) and
  then plays those seats behind one `Budget`, like `arena run --models`. The
  server refuses model seats unless it was started with
  `ARENA_ALLOW_MODEL_SEATS=1`, the request must carry `confirm_spend: true`,
  and the provider's key must be set; otherwise nothing is recorded or sent.
  A cost cap ends the match as `interrupted`. Model matches are rated like
  bot matches: one profile per model and personality (D-081).
  Every match records who sat where (`seats`: name, model id, kind) and
  whether it was played here or imported (`origin`).
- **Why:** The project owner wants to start and watch real matches from the
  UI. The API has no login and listens on localhost, so anything on the
  machine could start paid matches: off by default plus an explicit flag per
  request keeps a mistake from spending. Seats with names are what viewers
  read instead of p1..pN.
- **Alternatives:** Authentication (a bigger change, not needed on loopback
  yet); model seats always on (any local script could spend); a separate
  table for seats (the record is read with the match anyway).
