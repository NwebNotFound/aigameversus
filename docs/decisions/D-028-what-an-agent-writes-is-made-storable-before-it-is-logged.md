# D-028 · What an agent writes is made storable before it is logged

- **Date:** 2026-11-11
- **Decision:** The engine cleans every reply before it uses it: NUL
  characters and halves of surrogate pairs are removed from all strings, NaN
  and infinity become null.
- **Why:** Postgres refuses all three in `jsonb`, and model output goes into
  the log as thoughts, arguments and error texts. Without this, one odd
  character in one answer would stop a match at the next write.
- **Alternatives:** Rejecting such answers (costs a correction for something
  the model cannot see); cleaning in the store (the stored log would differ
  from the events the match applied, against D-016).
