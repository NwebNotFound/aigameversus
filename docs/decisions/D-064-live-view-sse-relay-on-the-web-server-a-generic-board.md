# D-064 · Live view: SSE relay on the web server, a generic board, spoilers in the UI

- **Date:** 2026-11-11
- **Decision:**
  - The browser follows a match through `GET /matches/<id>/stream` on the web
    server, as server-sent events. The web server reads the arena's WebSocket
    and sends each event with its `seq` as the SSE id. Close 1000 becomes an
    `end` event, 4404 `missing`; any other close just ends the response, and
    the browser's EventSource reconnects. The relay skips the positions up to
    `Last-Event-ID`; the page also keeps each position once, so a reconnect
    from the start shows nothing twice.
  - Board, cost and controls come from `GET /matches/<id>/state` (web server),
    reloaded after new events, at most about three times a second. Controls go
    to the same URL as `POST {action}`.
  - Columns: an event with `visible_to = null` is public (middle); every other
    event, thoughts included, is behind the scenes (right). The player filter
    keeps the events whose `player`, `caller` or `target` is that player, or
    that the player may see. Newest events come first.
  - One generic board draws every `render_spec` with `seats` as cards with
    their fields as text; a spec without seats is shown as JSON. The game
    tables of steps 5.4 and 5.5 replace it per `layout`.
  - Spoilers are a UI setting, on by default (spectators see everything,
    DESIGN). Off hides the board fields `hand`, `cards` and `role` and the
    whole right column. The list of secret fields lives in the UI
    (`web/src/lib/live.ts`), not in the plugins.
  - Cost shows four decimals of a euro, rounded up like the ledger.
- **Why:** SSE keeps the rule of D-030 (no browser call to the arena, no CORS)
  and brings reconnects with a resume position for free. Reloading the board
  from the API keeps the board logic in the plugin; the UI never rebuilds
  state. A fixed list of secret fields covers the three games with a board
  today without changing their plugins.
- **Alternatives:** a WebSocket proxy in the Node server (it would need a
  custom server around the adapter's handler); browser calls to the arena with CORS; spoiler marks in each
  `render_spec`; boards built from the events in the browser.
