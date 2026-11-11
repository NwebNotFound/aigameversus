# D-070 · Real models take their seats from the command line first

- **Date:** 2026-11-11
- **Decision:** `arena run --game <id> --models <id>,<id>,...` is the first
  and for now the only way to start a match with real models. Each named
  model from `config/models.yaml` takes one seat, in order. The command
  builds one `Budget` for the match, so it needs `DATABASE_URL`; it records
  the match and its events in the same tables as the API. When a cost cap
  is reached it does not ask: the match is closed as `interrupted` and the
  command exits with 3. After the match it prints what each seat cost from
  the ledger and checks that the stored log rebuilds the final state;
  `--save FILE` writes seats, result, cost and all events as JSON. Which
  model sat where is in the ledger rows and in the saved file, not in the
  event log.
- **Why:** The first real matches are run by hand, one at a time, by whoever
  holds the key, and a command in a terminal is the smallest thing that
  does that with the caps in force. A match that stops at a cap cannot
  overrun while nobody watches. The API keeps seating bots only until the
  UI can show a pause and ask.
- **Alternatives:** Model seats in `POST /matches` first (needs the pause
  question in the UI and a way to keep a key out of requests); a script
  outside the package (would not be tested with the rest); raising the cap
  from a prompt in the terminal (a second way to spend that tests cannot
  cover).
