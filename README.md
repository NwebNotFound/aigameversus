# AIGameVersus

An arena where AI models play games against each other while humans watch:
what each model says at the table, and what it secretly thinks.

It is not one game but a platform. Every game is a plugin; the model
connection, memory, spectator view, replays and rankings work for all of them.
The first build targets four games: *Liar's Deck* (a bluffing card game with a
revolver), No-Limit Texas Hold'em, Werewolf, and *Throne of Tokens* (a Civ-like
strategy game).

> **Status: early.** The engine core runs complete matches with random bots,
> stores every match as an event log and rebuilds any moment of it from that
> log (roadmap step 1.3), so far only for a small reference game. None of the
> four games exists yet.

<!-- Screenshot placeholder: live match view and match GIFs arrive with the spectator UI (phase 5). -->
*Screenshots and match GIFs will appear here once the spectator UI exists.*

## Quick start

Requires Docker with Compose. From the repository root:

```bash
docker compose up --build
```

That builds and starts five services, each with a healthcheck:

| Service | Address | Notes |
| --- | --- | --- |
| Web UI | <http://localhost:3100> | placeholder page until phase 5 |
| Arena API | <http://localhost:8100> | `GET /health`, interactive docs at `/docs` |
| PostgreSQL | `localhost:5433` | user and database `arena`; holds the match event logs |
| Redis | `localhost:6380` | match queue; today only the worker pings it |

All ports bind to `127.0.0.1` only. Stop with `docker compose down` (add
`--volumes` to also delete the database).

Configuration is optional for now. To change the database password or, later,
add a model API key, copy `.env.example` to `.env` and edit it. `.env` is
gitignored.

## Cost safety

Matches with real models go through paid APIs, so cost control is part of the
platform, not an afterthought.

- Today nothing in this repository can call a model. Development, tests and CI
  use random bots and a mock LLM only, and CI has no access to any API key.
- Model calls will ship together with hard caps: €0.50 per match and €5 per
  month by default. At a cap the match pauses and asks; it never keeps billing
  silently.
- API keys live only in `.env`. They are never written to code, logs or the UI
  (the UI shows them masked).

## Development

Python 3.12 and [uv](https://docs.astral.sh/uv/) are the only local
requirements besides Docker.

```bash
uv sync                      # create .venv from the lockfile
docker compose up -d db      # Postgres for the database tests (skipped without it)
uv run pytest                # tests
uv run ruff check .          # lint
uv run ruff format --check . # formatting
```

Secret scan, the same command CI runs:

```bash
docker run --rm --volume "$PWD:/repo" ghcr.io/gitleaks/gitleaks:v8.30.1 git /repo --redact --no-banner
```

On Windows, run these in Git Bash with `PYTHONIOENCODING=utf-8`; see
[CLAUDE.md](CLAUDE.md) for details.

## Layout

```
arena/      core: API, engine, agent runner, memory, game master
games/      one plugin package per game
config/     models and personalities (YAML)
mods/       extra content that overrides or extends game data
web/        spectator UI
docs/       design spec, decisions, credits
tests/      tests for the arena core
```

## Documentation

- [docs/DESIGN.md](docs/DESIGN.md): the full design spec (German).
- [docs/DECISIONS.md](docs/DECISIONS.md): decisions taken where the spec is open or overridden.
- [docs/CREDITS.md](docs/CREDITS.md): origin of every asset.
- [CLAUDE.md](CLAUDE.md): architecture and conventions for contributors, human or AI.
