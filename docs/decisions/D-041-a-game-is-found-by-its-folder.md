# D-041 · A game is found by its folder

- **Date:** 2026-11-11
- **Decision:** `arena/games.py` lists the games: every package `games/<id>/`
  with a `plugin.py` that defines exactly one `GamePlugin` class whose `id` is
  the folder name. The class is created without arguments. A package without
  `plugin.py` is skipped (data of a game that is not written yet); a
  `plugin.py` that breaks the rule stops the start with an error that names
  it.
- **Why:** The spec promises that a new game is a new folder and nothing
  else. One rule, checked at start, also keeps a game id, its folder and its
  stored logs under one name.
- **Alternatives:** A list of games in code or config (a second place to
  edit); entry points (packaging for something that lives in this repo);
  skipping broken folders (a game silently missing from the list).
