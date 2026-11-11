# Decisions

Decisions taken where [DESIGN.md](DESIGN.md) is open, or where this project
deliberately differs from it. `DESIGN.md` is kept verbatim as the original
spec; where the two disagree, this file wins.

Each entry: date, decision, why, alternatives considered.

## D-001 · Answers to the spec's open questions

- **Date:** 2026-11-11
- **Decision:** Frontend is SvelteKit. The in-game language is a per-match
  setting, default German. The default budget is €0.50 per match with a hard
  cap of €5 per month; at a cap the match pauses and asks. The default roster
  is a set of cheap OpenRouter models, listed in `config/models.yaml` when
  model calls land (step 1.5).
- **Why:** Set by the project owner before the build started.
- **Alternatives:** React; a fixed language; per-day instead of per-month cap.

## D-002 · Host ports 8100 / 3100 / 5433 / 6380, bound to 127.0.0.1

- **Date:** 2026-11-11
- **Decision:** Arena API on 8100, web UI on 3100, PostgreSQL on 5433, Redis on
  6380. Container ports stay standard. Every published port binds to
  `127.0.0.1`.
- **Why:** Non-default ports avoid clashes with other local stacks and with a
  host-installed Postgres or Redis (the spec says 3000 for the UI). Loopback
  only, because the API has no authentication and will be able to start paid
  matches, and the database uses a development password.
- **Alternatives:** Default ports; binding to all interfaces.

## D-003 · No restart policy in Compose

- **Date:** 2026-11-11
- **Decision:** Services have no `restart:` policy.
- **Why:** This is a development and spectator stack that you start on
  purpose. With a restart policy it would come back with every Docker start and
  could resume matches that spend money.
- **Alternatives:** `restart: unless-stopped`.

## D-004 · uv with a lockfile, hatchling, ruff

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

## D-005 · Static web placeholder until phase 5

- **Date:** 2026-11-11
- **Decision:** The `web` service is nginx serving one static page. The
  SvelteKit app replaces it in phase 5.
- **Why:** The Compose topology and port are fixed from the start, without
  carrying a Node toolchain, lockfile and CI job through four phases that do
  not touch the UI.
- **Alternatives:** An empty SvelteKit scaffold now.

## D-006 · Worker placeholder with a heartbeat healthcheck

- **Date:** 2026-11-11
- **Decision:** Until matches exist, the worker only pings Redis every 5 s and
  touches a heartbeat file after each successful ping. Its healthcheck fails
  when the heartbeat is older than 15 s. The worker does not exit when Redis is
  down; it goes unhealthy and recovers on its own.
- **Why:** The healthcheck then tests what matters for a worker (the process is
  alive and reaches its queue) rather than only that a container exists.
- **Alternatives:** No worker service until step 1.6; a healthcheck that opens
  its own Redis connection, which would not notice a hung worker.

## D-007 · Secret scan with a pinned gitleaks image

- **Date:** 2026-11-11
- **Decision:** CI scans the full git history with
  `ghcr.io/gitleaks/gitleaks` at a pinned version, run through `docker run`.
- **Why:** The same command runs locally and in CI, with nothing to install
  and no licence key.
- **Alternatives:** `gitleaks-action`; trufflehog; GitHub secret scanning alone.

## D-008 · Pinned service images: PostgreSQL 18, Redis 8, nginx 1.30

- **Date:** 2026-11-11
- **Decision:** `postgres:18-alpine` (volume mounted at `/var/lib/postgresql`,
  the layout that image expects since version 18), `redis:8-alpine`,
  `nginx:1.30-alpine`, `python:3.12-slim`.
- **Why:** Current stable majors, pinned so a rebuild does not change behaviour
  silently. Python 3.12 is the version the spec names.
- **Alternatives:** `latest` tags; an image with pgvector, which is deferred
  until the memory layer needs it (phase 6).
