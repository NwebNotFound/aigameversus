# D-004 · uv with a lockfile, hatchling, ruff

- **Date:** 2026-11-11
- **Decision:** Dependencies are managed with uv and pinned in `uv.lock`; the
  Docker image and CI install with `uv sync --frozen`. The project is an
  installable package (hatchling) containing `arena` and `games`. ruff does
  linting and formatting. `docs/DESIGN.md` is excluded from ruff because the
  spec is kept verbatim.
- **Why:** One lockfile gives the same versions locally, in CI and in the
  image. An installable package is needed for the `arena` command (step 1.6).
  One tool for lint and format keeps CI short.
- **Alternatives:** pip with `requirements.txt`; Poetry; black plus flake8.
