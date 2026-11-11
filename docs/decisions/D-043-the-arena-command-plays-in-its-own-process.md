# D-043 · The `arena` command plays in its own process

- **Date:** 2026-11-11
- **Decision:** `arena run --game <id> --bots` runs the engine in the command's
  own process and prints every event with its position and audience. It uses
  no server and no database and stores nothing. `--bots` is required: it is
  the only kind of player the command offers so far. A seed is chosen and
  printed when none is given.
- **Why:** The first thing anyone tries should work with `uv run` alone and
  cost nothing. Printing the seed makes every run repeatable.
- **Alternatives:** A command that calls the API (needs the stack; the API
  can be called with curl); storing command-line matches when a database is
  configured (behaviour that depends on the environment).
