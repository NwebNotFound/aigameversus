# D-040 · A match has a turn limit

- **Date:** 2026-11-11
- **Decision:** `GamePlugin.max_turns` is the most turns a match of the game
  can take; the default is 10 000 and a game sets its own (High Card: one
  turn per card, 20). `Match(max_turns=...)` overrides it for one match. When
  a match is still not over after that many completed turns, the engine logs
  `turn_limit_reached` (spectators only), hands the log to the sink and raises
  `PluginError`. A turn dropped by a pause does not count.
- **Why:** The engine already stops a turn without progress, but a plugin bug
  can also make progress forever: rounds that never end the game. Such a
  match would fill the event store and, with models, spend up to the cost
  cap. A limit on the plugin sits next to the rules that justify it.
- **Alternatives:** A time limit for the whole match (depends on how fast the
  models answer, and a pause would need an exception); a limit on events
  (harder to derive from the rules of a game); only a per-match setting (every
  caller would have to know every game).
