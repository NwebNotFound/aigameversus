# D-080 · The spectator UI: one watch screen, the transcript as its only text, two viewer modes

- **Date:** 2026-11-11
- **Decision:** `docs/UI-DESIGN.md` sets the look. Live view and replay become
  one "watch" screen: the board as a large stage, one commentary column built
  from `TranscriptLine` (`kind`, `importance`), and a timeline with chapters
  and highlight markers. There are two named viewer modes: "Spectator view"
  (the default: thoughts, hands and roles visible) and "Spoiler-free". In
  spoiler-free mode the transcript is fetched with `spoilers=false`. The web
  server strips spectator-only events and the secret board fields before they
  reach the browser, and there is no seed and no export.
- **Why:** The audit (screenshots of the bot demo at 375 and 1280) found raw
  engine lines, three equal columns with a small board, pages 11–17k px tall on
  mobile, and replays without rounds or highlights. One text source keeps the
  CLI, the API and the UI from telling a match in different words.
- **Alternatives:** Keep three equal columns and polish them (keeps the board
  small); a formatter in the browser (a second wording to keep in sync); hide
  thoughts by default (hides the project's main attraction).
