# D-075 · Match memories, the memory block, memory off and reset

- **Date:** 2026-11-11
- **Decision:**
  - When a match is remembered, every seated profile gets one summary of it
    from its own view (`match_memories`, migration `0009`, in the same
    transaction as the trust). The default `TemplateSummarizer` names the game,
    the opponents, the player's place and at most two notes per opponent, from
    the facts that player saw. No model is called; a `Summarizer` can.
  - `memory_block(store, me, opponents)` reads only the player's own rows and
    only about the profiles at the table: relationship lines first (strongest
    feeling first, three notes each), then up to five summaries of matches
    against them, newest first. It stops at the first line that does not fit
    1,200 characters and is None when the player knows nobody there.
  - The prompt puts the block before the game data, inside `<memory>`, with
    `<` escaped; the system message names it as data like the other blocks.
    `ModelAgent(memory=...)` takes it; without one the prompt is unchanged.
  - `memory: false` on a match (API, stored on the match record, a checkbox in
    the new-match form) remembers nothing. The form's box says "without memory",
    so a form that leaves it out keeps memory on.
  - Reset forgets relationships and summaries of one profile or of everyone
    (`POST /memory/reset`, `arena memory reset --yes`); ratings stay, and a match
    already remembered is not remembered again. There are no seasons yet: a
    season starts with a reset of everyone.
  - `arena run --models` does not build a block yet; the next part wires it in.
- **Why:** The spec's long-term layer and the "only the players at the table,
  kept short" rule; the block is built from the player's own rows, so it
  cannot carry another player's secrets. A profile's memories can name roles
  ("turned out to be a wolf", "hunted with me in the pack"): they are the
  same notes as on its relations page, written only for finished matches, so
  they reveal nothing about a match still being played, and spectators see
  every role anyway.
- **Alternatives:** the block in the system message (it is data, not an
  instruction); summaries written by a model now (costs money for every match);
  a season column on every memory row (no seasons exist yet).
