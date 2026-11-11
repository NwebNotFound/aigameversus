# D-086 · The watch screen: spoiler-free by allowlist in the web server, playback by moments

- **Date:** 2026-11-11
- **Decision:** The live view and the replay share one component
  (`WatchScreen`): the cast, the board and a commentary column made of
  transcript lines (D-078), drawn by `kind`. Bookkeeping (importance 1) is
  folded unless the viewer shows it. In the spoiler-free view
  (`?view=spoiler-free`), the SvelteKit server drops every event that is not
  public from the log and the live stream. It removes the seed. It passes each
  board through an allowlist per layout (`web/src/lib/server/redact.ts`):
  hidden cards become placeholders, roles become null, and an unknown field or
  layout is dropped. The transcript is fetched with `spoilers=false`. Switching
  the view is a page load that keeps the event shown. Replay play and step
  move from moment to moment (lines of importance 2 and up, chapter headings)
  instead of event by event, or from highlight to highlight. A chapter button
  is drawn for every numbered heading (round, hand, night, day).
- **Why:** Nothing hidden may reach the browser in the spoiler-free view, and
  an allowlist keeps a new secret field hidden by default, where a list of
  secret names would leak it. Stepping by events showed long runs of
  bookkeeping, which the audit found to be the main reason why replays felt
  slow and unreadable.
- **Alternatives:** A `spoilers=false` parameter on the arena's board and
  events endpoints (cleaner, but a change to the core; the web filter can stay
  as a second guard when it comes). Hiding the hidden data with CSS (it would
  still be in the page). Playback by fixed time per event (spends most of the
  time on bookkeeping).
