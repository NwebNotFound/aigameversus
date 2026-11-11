# D-042 · Matches from the API run inside the API process; spectators read the log over WebSocket

- **Date:** 2026-11-11
- **Decision:** `POST /matches` starts a match as an asyncio task of the API
  process. Its events are stored turn by turn; `WS /matches/{id}/events`
  sends the log from its first event, waits for new turns while the match
  runs, and closes when it stops. A match that is over is sent from the event
  store. Only completed turns are shown. A `matches` row holds what was asked
  for and how it ended: `running`, `finished`, `failed`, `interrupted`. When
  the server stops, its matches stop; the next start marks them
  `interrupted`. `turn_delay` (0 to 60 s) paces a match for watching. Seats
  are random bots only until model seats come with phase 2. The server plays
  at most 10 matches at a time and answers 429 to a start beyond that; with
  the turn limit (D-040) this bounds what requests can make it store. The server speaks
  WebSocket through the `websockets` package, a dependency of its own because
  plain `uvicorn` brings none.
- **Why:** One process needs no queue and no message bus to get a live
  stream, and a bot match lasts milliseconds. Sending the log from the start
  gives a late spectator, a reconnect and a replay the same simple protocol,
  and the stream can never show something that is not stored. A match cannot
  be continued in another process yet, so saying `interrupted` is the honest
  status.
- **Alternatives:** Running matches in the worker with Redis for the stream
  (the Compose services exist for it; worth it once matches are long or
  many); server-sent events (the UI will also send controls); streaming only
  new events and loading the past over HTTP (two code paths in every client);
  continuing interrupted matches from the log (needs agents that can be
  rebuilt; later).
