# D-017 · Database tests use a real Postgres, one schema per test

- **Date:** 2026-11-11
- **Decision:** Tests under `tests/db/` connect to the Compose database on
  `127.0.0.1:5433` (or `ARENA_TEST_DATABASE_URL`), each in a fresh schema that
  is dropped afterwards. Without a reachable server they are skipped locally;
  with `CI` set they fail. CI starts Postgres as a service container.
- **Why:** The store is SQL, so only the real database proves it. Schemas keep
  tests independent of each other and of development data.
- **Alternatives:** Mocking the driver; an in-memory fake store; testcontainers.
