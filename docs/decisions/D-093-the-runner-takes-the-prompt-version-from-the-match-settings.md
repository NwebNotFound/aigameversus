# D-093 · The runner takes the prompt version from the match settings

- **Date:** 2026-11-11
- **Decision:** `ModelAgent` gets the match settings. It asks the game for
  `rules(settings)` once and for `situation_summary(observation, settings)`
  every turn, and puts the summary in a `<summary>` block above
  `<situation>`; the system message then names that block too. The match
  records `prompt_version(settings)` in `match_started` and in its record
  (column `matches.prompt_version`, also in `/replays`), and `arena run
  --save` writes it into the export. A `-p2` version always means its rules
  and its summary together, so the id says exactly what the models read. Without a summary the prompt is the one
  from before, byte for byte (the p1 golden files check it).
- **Why:** Poker and Werewolf have a second prompt version (new rules, a
  summary of the turn), and an A/B comparison needs every match to say which
  one its models read. The summary comes first because models read the top
  and the end of a prompt most closely; it is built from the observation, so
  it cannot leak what the player may not see.
- **Alternatives:** The summary inside `<situation>` (mixes text with the
  JSON a mock model parses); the version only in the settings (a default
  would not show up in the log, and the default may change); a summary in
  the system message (that one is meant to be the server's words, not game
  data).
