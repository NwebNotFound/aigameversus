# D-072 · Replays: one event per step, the board from the API, the step in the address

- **Date:** 2026-11-11
- **Decision:**
  - A replay steps through the stored log one event at a time: step N shows the
    first N events (0 is before the match, the log length its end). Opened
    without a step, a replay shows the whole match.
  - The board of a step comes from `GET /matches/{id}/board?events=N`, which
    replays that prefix and returns the game's `render_spec`. The player loads
    it through the web server, keeps every board it has seen and leaves the last
    one up while the next loads. The columns are the live view's, through one
    shared component (`MatchColumns`).
  - Play advances one step per tick (0.5× to 4×, 1000 to 125 ms) and stops at
    the end. The step is kept in the address (`?step=N`, without a new history
    entry), so a copied address or the share link opens the same place.
  - `GET /replays` lists the newest 100 finished matches with their winners
    (rank 1) and the cost of their model calls, in one query. Failed, aborted
    and interrupted matches are not replays.
  - The JSON export (`/replays/<id>/export.json`, format
    `aigameversus-replay/1`) is the match record, its cost and the whole log as
    spectators see it, thoughts and hidden cards included; replaying the log
    rebuilds the match.
- **Why:** The event is the smallest unit the log has, so no step hides
  anything; the board stays the plugin's drawing, never rebuilt in the browser.
- **Alternatives:** steps per turn (the log has no turn marker every game
  shares); boards for all steps at once (hundreds of replays per load);
  exporting only public events.
