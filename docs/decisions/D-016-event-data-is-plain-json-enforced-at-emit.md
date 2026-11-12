# D-016 · Event data is plain JSON, enforced at emit

- **Date:** 2026-11-11
- **Decision:** The engine rejects a game event whose data would change in a
  JSON round trip (tuples, non-string keys) and stops the match with a plugin
  error.
- **Why:** The live state is built from the same events that are stored. If
  storage changed an event, a replay would differ from the match. Checking at
  emit finds this in every bot match, without a database.
- **Alternatives:** Normalising silently; finding it only in database tests.
