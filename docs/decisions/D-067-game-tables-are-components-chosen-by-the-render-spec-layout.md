# D-067 · Game tables are components chosen by the render_spec layout

- **Date:** 2026-11-11
- **Decision:** The live view's `Board` picks a table component by the `layout`
  of the plugin's `render_spec` (`card_table` is the Liar's Deck bar table in
  `web/src/lib/components/LiarsDeckTable.svelte`) and falls back to the generic
  board when the spec does not have the fields the table needs. `Board` also
  gets the match log (`events`), so a table can react to what just happened.
  The Liar's Deck table shows a banner for each call ("Liar!") and each shot
  ("click" or "BANG") for 1.3 seconds, in order, at most six at a time, and
  never for the backlog it finds when it appears: replays and reloads do not
  replay the drama. The art is inline SVG and CSS, no files.
- **Why:** The spec is a plain dict, so the UI decides the drawing; falling back
  keeps the live view working for a game without a table. Reading the log
  keeps the plugin free of animation state.
- **Alternatives:** an animation field in `render_spec` (puts UI state in the
  plugin); one component per game chosen by game id (breaks for variants that
  share a layout).
