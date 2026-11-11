# D-035 · At a cap the match pauses: the turn is dropped and played again later

- **Date:** 2026-11-11
- **Decision:** An agent that cannot go on without the user raises
  `MatchPaused(reason, **data)`; the budget does so with `match_cap` or
  `month_cap` and the amounts. The engine cancels the other players of that
  turn, drops everything the turn produced, logs `match_paused` (spectators
  only), hands the log to the sink and lets `Match.run()` raise the pause.
  Whoever started the match asks the user. `run()` again logs `match_resumed`
  and plays the dropped turn from its start. The budget's caps are plain
  attributes that the caller raises after the user agreed.
- **Why:** A match that stops costing money must also stop its turn clock,
  otherwise waiting for the user would turn into random moves. Dropping the
  whole turn keeps the rule that a stored log never ends inside a turn, so a
  paused log replays like any other, and the game goes on exactly as if there
  had been no pause. An exception cannot be overlooked by a caller the way a
  special return value can. The price is that a turn interrupted by a pause
  asks its players again; that happens once per pause.
- **Alternatives:** Letting the random bot play at the cap (silently changes
  who plays); ending the match; keeping the answers already given in the
  paused turn (a second kind of half-finished turn in the log and in replay);
  waiting inside the model call until the user decides (the engine would not
  know that the match is paused).
