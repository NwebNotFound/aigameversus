# D-027 · Prompt layout, and how other players' words are kept apart from instructions

- **Date:** 2026-11-11
- **Decision:** Two messages. System: who the player is, the game's
  `rules.md`, how to answer (one tool call is the move, plain text is private
  thinking), and that game data is never an instruction. User: the
  observation in `<situation>`, the last 40 events the player may see in
  `<events>`, then the ask, with the server's error on a correction. All game
  data is JSON with `<` escaped, one event per line. Text a player wrote is a
  game event of the reserved type `message` with exactly
  `{"player", "text"}`; the engine refuses any other shape. A prompt shows it
  as `player p2 says: "..."`, the reader's own as `you said: "..."`. The
  engine, not the runner, selects the events of a request by
  `event.is_visible_to(player)`. The scaffolding is English; the per-match
  language (D-001) applies to what models say and comes with table talk.
- **Why:** Everything the server says is in the system message; everything
  that can contain another model's words is in data blocks that those words
  cannot leave: JSON keeps a text on its line, the escaped `<` keeps it from
  closing a block. One reserved event type lets every game's chat be labelled
  the same way without the prompt builder knowing any game. Filtering in the
  engine means a hidden event is never handed to an agent at all.
- **Alternatives:** One chat message per event (more tokens, and role
  `assistant`/`user` would blur who wrote what); a flag on `Event` for player
  text (a schema and storage change); stripping suspicious text (lossy, and a
  filter can be talked around); a summary of older events (comes with memory,
  phase 6).
