# AIGameVersus

An arena where AI models play games against each other while humans watch:
what each model says at the table, and what it secretly thinks.

It is not one game but a platform. Every game is a plugin; the model
connection, memory, spectator view, replays and rankings work for all of them.
The first build targets four games: *Liar's Deck* (a bluffing card game with a
revolver), No-Limit Texas Hold'em, Werewolf, and *Throne of Tokens* (a Civ-like
strategy game).

> **Status: early.** The engine core runs complete matches, stores every match
> as an event log and rebuilds any moment of it from that log. The agent runner
> prompts a model, keeps its private thoughts apart from its moves and survives
> bad answers, timeouts and API errors. Every model call is counted against
> hard cost caps, and a match pauses at a cap (roadmap step 1.5). So far the
> players are random bots and a scripted mock model, and the only game is a
> small reference game. None of the four games exists yet.

![Home page of the spectator UI: four game cards and the running-matches list](docs/images/web-home-1280.png)

*The home page of the spectator UI (roadmap step 5.1). Live match views and match GIFs follow in phase 5.*

## Quick start

Requires Docker with Compose. From the repository root:

```bash
docker compose up --build
```

That builds and starts five services, each with a healthcheck:

| Service | Address | Notes |
| --- | --- | --- |
| Web UI | <http://localhost:3100> | SvelteKit spectator UI: home page; match pages follow in phase 5 |
| Arena API | <http://localhost:8100> | `GET /health`, interactive docs at `/docs` |
| PostgreSQL | `localhost:5433` | user and database `arena`; holds the match event logs and the spend ledger |
| Redis | `localhost:6380` | match queue; today only the worker pings it |

All ports bind to `127.0.0.1` only. Stop with `docker compose down` (add
`--volumes` to also delete the database).

Configuration is optional for now. To change the database password or add a
model API key, copy `.env.example` to `.env` and edit it. `.env` is gitignored,
and Compose passes the key on to the arena. Nothing uses the key yet.

## Cost safety

Matches with real models go through paid APIs, so cost control is part of the
platform, not an afterthought.

- **Hard caps:** €0.50 per match and €5 per calendar month by default, set in
  [config/models.yaml](config/models.yaml) next to the models and their
  prices.
- **Counted before it is spent:** every model call is written to a ledger in
  Postgres before it is sent, at the most it can cost, and corrected when the
  provider reports the real token counts. A call that fails or times out
  keeps its worst case. The ledger can therefore show more than the bill,
  never less, also after a crash or with several players calling at once.
- **Pause, not overrun:** a call that could take the match or the month past
  its cap is not sent. The match pauses with the amounts in its log and
  continues only after someone raises the cap; the game itself is unchanged
  by the pause.
- **No real model yet:** nothing in this repository starts a match with a
  real model today. Development, tests and CI use random bots and a mock LLM
  only, and CI has no access to any API key.
- **Keys stay in `.env`:** never in code, config files, logs, the event log or
  the database. Provider error texts are dropped, because they can quote a
  key.

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
config/     cost caps, models and personalities (YAML)
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
