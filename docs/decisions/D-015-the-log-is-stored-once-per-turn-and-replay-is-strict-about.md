# D-015 · The log is stored once per turn, and replay is strict about versions

- **Date:** 2026-11-11
- **Decision:** A match hands its new events to the store after setup, after
  every completed turn and at the end, each batch in one transaction with
  explicit positions (`match_id`, `seq` is the primary key). `replay` refuses a
  log whose game id or plugin version differs from the plugin it is given.
- **Why:** A stored log then always ends at a turn boundary, so a crashed match
  can be replayed to a state the game really had, and a second writer for the
  same match fails instead of interleaving. A plugin of another version may
  apply old events differently; failing loudly beats a silently wrong state.
  The stored events themselves stay readable for any version.
- **Alternatives:** One write per event (a crash could cut a turn in half);
  replaying across versions and hoping.
