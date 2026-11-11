# CLAUDE.md

Guide for anyone, human or AI, who continues this project. Read it together
with [docs/DESIGN.md](docs/DESIGN.md) (the spec, German) and
[docs/DECISIONS.md](docs/DECISIONS.md) (where the spec is open or overridden;
it wins over the spec).

## What this is

AIGameVersus is an arena, not a single game. AI models play turn-based games
against each other; humans watch. Each game is a plugin. Model connection,
memory, spectator UI, replays and rankings are shared by all games.

**State of the build:** roadmap step 1.3. The engine runs complete matches of
any plugin with random bots, stores their event logs in Postgres and rebuilds
the state from a log. There is one reference game, High Card (`games/toy`). The
arena API still exposes only `GET /health` (it migrates the database at
startup), the worker is a heartbeat placeholder, the web UI is a static page. Sections below marked *not
built yet* describe the target from the spec and get filled in as their phase
lands.

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

### One turn

`arena/engine/match.py` runs this loop until the plugin says the game is over:

1. Ask the plugin who is active. Each active player gets a `TurnRequest`: their
   observation and the tools allowed now. In a simultaneous game all active
   players decide on the same state.
2. The agent answers with one `Action`. The engine checks the tool name, then
   the arguments against the tool's JSON Schema, then the plugin's `validate`.
   A rejected action goes back with a clear error, up to 2 corrections. After
   that the game's `random_action` plays and the turn is marked
   (`action_fallback`).
3. `apply_actions`, then `step`, let the plugin emit game events.
4. A turn without a game event is a plugin bug and stops the match.

*Not built yet:* prompts and model calls (step 1.4), streaming to the UI (1.6).

### Events and state

A match is a list of `Event`s. Engine events (`match_started`,
`action_accepted`, `action_rejected`, `action_fallback`, `match_finished`) are
bookkeeping. Game events come from the plugin through `ctx.emit` and are the
only thing that changes the game state: `emit` records the event and passes it
to the plugin's `apply_event` at once. Replaying the game events over
`initial_state` therefore rebuilds the exact state.

Every event says who may see it: `visible_to=None` is public, a list of
players is private to them, an empty list is spectators only. The seed is
spectators only.

Event data must be plain JSON (lists, not tuples; string keys), because a
stored event has to come back exactly as it was applied. The engine stops a
match that emits anything else.

### Storage and replay

- `replay(plugin, events)` in `arena/engine/replay.py` returns the state after
  a log, or after any prefix of it. It needs no seed and runs no rules. It
  refuses a log recorded by another game or another plugin `version`.
- `Match(..., sink=...)` hands over the new events once per completed turn, so
  a stored log never ends in the middle of a turn.
- `EventStore` in `arena/db/event_store.py` keeps logs in the `match_events`
  table: `sink=partial(store.append, match_id)` to write, `store.load(match_id)`
  to read.
- Schema changes are numbered SQL files in `arena/db/migrations/`. The arena
  applies new ones at startup. Add a new file; never edit one that has been
  merged.

### Randomness

`ctx.rng("deal", state.round_no)` returns a random stream derived from the
match seed and that key. Name the stream after what it decides and include a
counter; asking for the same key twice in a match is an error. Random bots and
the fallback use their own streams, so rejected attempts and bot choices never
shift the game's randomness.

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
  db/           connection pool, SQL migrations, event store
  worker.py     match worker process
games/          one package per game: plugin.py, rules.md, data, tests/
  toy/          High Card, the reference plugin
config/         models.yaml, personalities/*.yaml
mods/           content that overrides or extends game data
web/            spectator UI
docs/           DESIGN.md, DECISIONS.md, CREDITS.md
tests/          tests for the arena core
```

## Commands

```bash
uv sync                       # install into .venv from uv.lock
docker compose up -d db       # Postgres for the database tests (skipped without it)
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

Copy the shape of `games/toy/`, the smallest complete game.

1. Create `games/<id>/` with `__init__.py`, `plugin.py` and `tests/`.
2. Define the state as a Pydantic model and subclass `GamePlugin`
   (`arena/engine/plugin.py`). Set `id`, `version`, `min_players`,
   `max_players` and `turn_mode`.
3. `initial_state` builds the state before anything happened, without
   randomness, and raises `ValueError` for bad settings. `setup` emits the
   opening events (deal, assign roles).
4. Change the state only in `apply_event`. `setup`, `apply_actions` and `step`
   decide what happens and call `ctx.emit(type, data, visible_to=...)`.
5. `get_observation` returns only what that player may see, as a copy.
   `get_tools` returns the allowed actions as `ToolSpec`s with a JSON Schema.
   `validate` returns `None` or a message that tells the player how to fix the
   action.
6. `random_action` picks a random legal action from an observation. It is the
   game's random bot and the engine's fallback.
7. Tests, as in `games/toy/tests/`: full bot matches for every player count,
   same seed gives the same events and state, observations do not depend on
   other players' hidden information, private events are private, rejected
   actions carry a useful message.

*Not built yet:* `rules.md` for model prompts (step 1.4), the registry that
finds games by id (1.6), and what the UI needs to draw a game (phase 5).

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
