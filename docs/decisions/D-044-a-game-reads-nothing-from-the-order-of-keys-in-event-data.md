# D-044 · A game reads nothing from the order of keys in event data

- **Date:** 2026-11-11
- **Decision:** Event data is JSON whose objects have no order: plugins use a
  list wherever order matters. `tests/test_games.py` plays a bot match of
  every game and replays its log with the keys of every object reversed.
- **Why:** Postgres `jsonb` does not keep key order, and the engine's check
  that event data survives JSON (D-016) compares with `==`, which ignores
  order. A plugin that iterated over such an object would replay differently
  from how it played.
- **Alternatives:** Storing events as `json` instead of `jsonb` (keeps the
  order in Postgres only, not in other stores or exports).
