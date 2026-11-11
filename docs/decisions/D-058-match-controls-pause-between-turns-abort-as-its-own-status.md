# D-058 · Match controls: pause between turns, abort as its own status

- **Date:** 2026-11-11
- **Decision:**
  - Pause, resume, speed and abort act on the match task in the API process
    (`LiveMatches`), not through the database. Only the process that plays a
    match can control it; any other match answers 409.
  - A pause takes effect after the current turn is stored and published, before
    the engine asks for the next turn. No agent, and so no model, is called
    while a match is paused. A pause is not logged as an event: it changes
    nothing in the game, and the same seed gives the same log with or without
    it.
  - A speed change applies at once, also to a wait that has already begun.
  - Abort cancels the task. The record gets the new status `aborted`
    (migration `0006`), with no placements; the stored turns stay readable.
    A match stopped by a server shutdown stays `interrupted`. Once the turn
    with `match_finished` is stored, the match is over: abort answers 409, and
    that last turn does not wait for a resume, so a match paused just before
    its end still ends `finished`. A record that is no longer `running` is
    never closed again.
  - `GET /matches/{id}/board` replays the stored log and returns the game's
    `render_spec`, or `null` for a game without one. `GET /matches/{id}/cost`
    sums the ledger per player.
- **Why:** The live view (roadmap 5.2) needs these controls; doing them in the
  process that owns the task needs no queue or polling. Pausing between turns
  keeps a pause free of cost and the log a clean list of turns.
- **Alternatives:** a `match_paused` event for spectator pauses (they are not
  game events, and a replay should not stop there); aborted matches as
  `failed` (it hides that nobody did anything wrong); a speed change only from
  the next turn (a 30 s wait would ignore the click).
