# D-095 · The spend ledger in a database of its own, the key in a file

- **Date:** 2026-11-11
- **Decision:** The ledger (`model_calls`) lives where `LEDGER_DATABASE_URL`
  points, by default the match database. The stack keeps it in a Postgres
  container of its own (`aigv-ledger`, not in the Compose project), dumped
  daily by `scripts/backup-ledger.sh`. The server starts without the ledger;
  a model match starts only when the ledger answers and is not empty beside
  finished model matches played here (503 otherwise; imported matches booked
  elsewhere). Every cost is read from the ledger, also the leaderboard's
  cost per game and the model page (`RatingStore.usage` maps the ledger's
  costs per seat to profiles). While it is down `/matches/{id}/cost`
  answers 503, and `/replays`, the leaderboard and the model page show every
  cost as null: the lists stay usable, and an unknown cost is not shown as 0. The stack gets the provider key as a read-only file
  (`OPENROUTER_API_KEY_FILE`), read at every start of a model match; model
  seats, ledger URL and key come in one override file,
  `docker-compose.models.yml`, and the plain stack has no key.
- **Why:** The month cap is a sum over the ledger. In the stack's database
  it would be reset by `docker compose down -v`, and a stack pointed at a new
  database would see an empty month and could spend the cap again. An empty
  ledger beside finished model matches is exactly that case. A key in the
  environment of Compose shows up in `docker inspect`; a file can be replaced
  without a restart.
- **Alternatives:** The ledger in the stack's database (reset with its
  volume); a check of the month against the provider's bill (needs a second
  key with billing rights, and comes late); refusing to start without the
  ledger (bot matches would stop too); a ledger migration set of its own (the
  ledger database gets all tables instead, unused ones stay empty).
