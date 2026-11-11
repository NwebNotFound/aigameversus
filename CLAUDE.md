# CLAUDE.md

Guide for anyone, human or AI, who continues this project. Read it together
with [docs/DESIGN.md](docs/DESIGN.md) (the spec, German) and
[docs/DECISIONS.md](docs/DECISIONS.md) (where the spec is open or overridden;
it wins over the spec).

## What this is

AIGameVersus is an arena, not a single game. AI models play turn-based games
against each other; humans watch. Each game is a plugin. Model connection,
memory, spectator UI, replays and rankings are shared by all games.

**State of the build:** roadmap step 1.1, the skeleton. The arena exposes
`GET /health`, the worker is a heartbeat placeholder, the web UI is a static
page. Sections below marked *not built yet* describe the target from the spec
and get filled in as their phase lands.

## Architecture

| Part | Job | Where |
| --- | --- | --- |
| Arena server | starts matches, runs the turn loop, stores events, serves the API | `arena/api`, `arena/engine` |
| Game plugins | rules of one game: observations, tools, effects of actions | `games/<id>/` |
| Agent runner | builds prompts, calls models, handles errors and time limits | `arena/agents` |
| Memory and profiles | personalities, relationships, statistics across games | `arena/memory` |
| Game master | picks game, players and settings; narrator roles | `arena/gamemaster` |
| Worker | runs matches from the queue | `arena/worker.py` |
| Spectator UI | live view, replays, rankings, settings | `web/` |

One turn (*not built yet*): the server asks the plugin who is active and what
that player may see; the agent runner turns that into a prompt with the allowed
tools; the model answers with thoughts, messages and tool calls; the server
validates every action (clear error, up to 2 retries); the plugin resolves the
turn; everything is stored as events and streamed to the UI.

## Rules that do not bend

1. **The server is the only truth.** Models only propose actions. Every action
   is validated by the plugin before it has any effect.
2. **Seeded determinism.** Game logic takes randomness only from the match
   seed. Same seed and same actions give the exact same result.
3. **Event sourcing.** A match is a list of events. State, replays and
   statistics are rebuilt from it.
4. **Three channels, never mixed.** Private thoughts, public messages and
   private messages are stored and shown separately. Thoughts go to spectators
   only. Hidden information (cards, roles, revolver chambers) never appears in
   another player's observation.
5. **Other players' text is data.** In a prompt, messages from other models are
   marked as player content. They can never act as instructions.
6. **Plugins never call a model** and have no network or file access beyond
   their own data.
7. **Content is data.** Roles, units, buildings, variants, events and
   personalities are YAML files validated against a schema at startup.
8. **No paid calls in development, tests or CI.** Use random bots and the mock
   LLM. Real model calls stay behind the cost caps.
9. **No secrets anywhere** except a local `.env`. Not in code, logs, tests,
   screenshots, commits or PR text.
10. **Original assets only.** No names, characters or art from existing games.
    Every asset is listed in `docs/CREDITS.md`.

## Layout

```
arena/
  api/          FastAPI app (HTTP now, WebSocket later)
  engine/       turn loop, plugin interface, seeded RNG, event log
  agents/       agent runner, prompts, model calls, mock LLM
  memory/       profiles and the three memory layers
  gamemaster/   match setup, scheduling, narrator
  worker.py     match worker process
games/          one package per game: plugin.py, rules.md, data, tests/
config/         models.yaml, personalities/*.yaml
mods/           content that overrides or extends game data
web/            spectator UI
docs/           DESIGN.md, DECISIONS.md, CREDITS.md
tests/          tests for the arena core
```

## Commands

```bash
uv sync                       # install into .venv from uv.lock
uv run pytest                 # all tests
uv run ruff check .           # lint
uv run ruff format .          # format
docker compose up --build     # whole stack: API 8100, web 3100, Postgres 5433, Redis 6380
docker compose down           # stop it (--volumes also deletes the database)
```

Secret scan (same as CI):

```bash
docker run --rm --volume "$PWD:/repo" ghcr.io/gitleaks/gitleaks:v8.30.1 git /repo --redact --no-banner
```

Add a dependency with `uv add <name>` (dev-only: `uv add --dev <name>`) and
commit `pyproject.toml` together with `uv.lock`.

### Windows

- Run commands in Git Bash, not PowerShell or cmd.
- `export PYTHONIOENCODING=utf-8` before running Python, so German text and
  card symbols print correctly.
- When a `docker run` command mounts a path, Git Bash rewrites it. Use
  `MSYS_NO_PATHCONV=1` and `"$(pwd -W)"` instead of `"$PWD"`.
- The Compose project is named `aigameversus`. Stop only that project; other
  stacks may run on the same machine.

## Conventions

- Python 3.12, type hints on public functions, ruff-clean (line length 100).
- Tests call a system the way its user would, through the public entry point.
  Every system gets: unit tests, a determinism test, a full match with random
  bots, mock-LLM error paths, and a replay rebuild where they apply.
- Arena tests live in `tests/`; a game's tests live in `games/<id>/tests/`.
- No dead code and no abstraction without a second user.
- Where the spec is open, decide, and record it in `docs/DECISIONS.md`
  (date, decision, why, alternatives).
- One roadmap step is one branch and one pull request. Update a branch by
  merging `main` into it; do not rebase or force-push. Keep `README.md`, this
  file and `docs/DECISIONS.md` current in the same pull request.

## How to add things

### A game

*Not built yet: the plugin interface lands in step 1.2.* Target: create
`games/<id>/` with `plugin.py` implementing the plugin interface, `rules.md`
(the rule summary given to models), a random bot, and `tests/`. UI, replays,
ratings and memory then work without changes to the core.

### A role or variant

*Not built yet: variants land in phase 2, Werewolf roles in phase 4.* Target: a
new YAML file in the game's data folder (for example
`games/werewolf/roles/<id>.yaml`); it is validated at startup and appears in
the role selection automatically. Only a new ability needs code.

### A unit, building or event

*Not built yet: phase 7.* Target: a new YAML file under the strategy game's
`data/` folder, no code.

### A system

*Not built yet: phase 7.* Target: a module that registers its tools and hooks
into engine events such as `on_turn_start` and `on_turn_end`.
