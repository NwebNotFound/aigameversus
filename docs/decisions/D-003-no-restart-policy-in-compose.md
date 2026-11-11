# D-003 · No restart policy in Compose

- **Date:** 2026-11-11
- **Decision:** Services have no `restart:` policy.
- **Why:** This is a development and spectator stack that you start on
  purpose. With a restart policy it would come back with every Docker start and
  could resume matches that spend money.
- **Alternatives:** `restart: unless-stopped`.
