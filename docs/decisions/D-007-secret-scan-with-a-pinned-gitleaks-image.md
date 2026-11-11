# D-007 · Secret scan with a pinned gitleaks image

- **Date:** 2026-11-11
- **Decision:** CI scans the full git history with
  `ghcr.io/gitleaks/gitleaks` at a pinned version, run through `docker run`.
- **Why:** The same command runs locally and in CI, with nothing to install
  and no licence key.
- **Alternatives:** `gitleaks-action`; trufflehog; GitHub secret scanning alone.
