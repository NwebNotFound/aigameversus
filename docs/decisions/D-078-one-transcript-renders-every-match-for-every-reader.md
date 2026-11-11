# D-078 · One transcript renders every match for every reader

- **Date:** 2026-11-11
- **Decision:** `arena/transcript/` turns the events of a match into readable
  lines, one per event, in English and German (`TranscriptLine`: `kind`, `actor`,
  `text`, `detail`, `importance`, `raw`). Each game has a renderer class with a
  `handle_<type>` method per event type; the engine's own events are handled once
  in the base class. A test reads the plugins' source and fails when one emits a
  type without a method. Hidden information (hands, roles, private choices,
  thoughts, whispers, the seed) is written only with `spoilers=True`; public talk
  always. `importance` is 1 for bookkeeping, 2 normal, 3 highlight; `kind` is one of
  heading, action, speech, whisper, thought, reveal, result, narration, info.
  It is served by `GET /matches/{id}/transcript?lang=&spoilers=&format=json|text|markdown`
  and printed by `arena run` (live, instead of raw events; `--raw` keeps them) and
  `arena transcript <match-id|file>`. Players are "Name (model)" where the match
  was rated or a file names its seats, else the seat id. The Werewolf narrator's own
  lines are shown only in the language the match was played in, as bookkeeping.
- **Why:** The live view, replays, exports and the terminal need the same words
  or they drift apart; one renderer per game, tested against what the plugins emit,
  keeps them equal. Keeping the raw event on each line lets a UI fold it away
  without a second request.
- **Alternatives:** a formatter in TypeScript for the web (a second copy to keep
  in step, and no help for the CLI); text written by the plugins themselves (puts
  words into rules code, and names are a presentation matter).
