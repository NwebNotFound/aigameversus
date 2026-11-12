# D-139 · A game keeps its old rules versions, and a stored match is read with its own

- **Date:** 2026-11-12
- **Decision:** When a game changes its rules or data, it raises its `version`
  and keeps the old versions it can still play. `GamePlugin.at_version(version)`
  returns the game with the rules of that version. `replay`, and through it every
  board and analysis of a stored match, asks for the version in the log's
  `match_started`, so a match is always read with the rules it was played with. A
  log without the field is version 1 (`replay.recorded_version`). A version the
  game does not have is refused with `ReplayError`, as before. Throne of Tokens
  does it with one data set per version: `games/civ/plugin.py` `RULES`, version 1
  being the data files with the two numbers of D-137 and D-138 set back. A golden
  bot match recorded by the version-1 code (`games/civ/tests/golden/v1_match.json`)
  must replay to its recorded state, and version 1 must still play it event for
  event.
- **Why:** The event log is the source of truth and the history is frozen (lead,
  2026-11-12). Version-1 matches include a paid smoke match with real model data,
  and they must stay readable and comparable. Raising the version alone would
  only have made them unreplayable.
- **Alternatives:** Replay every log with the newest rules (wrong as soon as a
  rule changes what an event means). Convert old logs to the new version (changes
  history). Delete old logs (loses paid data).
