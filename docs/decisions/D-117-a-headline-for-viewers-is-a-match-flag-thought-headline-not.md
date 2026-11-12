# D-117 · A headline for viewers is a match flag, thought_headline, not a prompt version

- **Date:** 2026-11-12
- **Decision:** With the match setting `thought_headline: true` every tool
  call asks, right after `thought`, for a required `headline` of at most 120
  characters (about 15 words): the thought in a line for the people watching.
  The runner takes it out of the call like the thought, cuts it at 120
  characters, and the spectators-only `thought` event keeps it as
  `headline`. Default `false`: nothing asks for or keeps a headline, and a
  model that sends one anyway is treated as before. The flag is the engine's,
  not the game's (`game_settings` removes it), is checked (a boolean) and is
  recorded in `match_started`.
- **Why:** Long thoughts make the watch screen a wall of text. A headline the
  model writes itself says what it means; a first sentence often does not.
  It is a flag rather than a prompt version because it is the same request in
  every game and must be combinable with any version; an experiment compares
  the same seeds with the flag on and off.
- **Alternatives:** A prompt version per game (one per game and per existing
  version); a short summary made by a second model (a paid call per move);
  only the first sentence (the fallback the UI uses without the flag).
