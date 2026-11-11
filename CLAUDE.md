# CLAUDE.md

Guide for anyone, human or AI, who continues this project. Read it together
with [docs/DESIGN.md](docs/DESIGN.md) (the spec, German) and
[docs/DECISIONS.md](docs/DECISIONS.md) (where the spec is open or overridden;
it wins over the spec).

## What this is

AIGameVersus is an arena, not a single game. AI models play turn-based games
against each other; humans watch. Each game is a plugin. Model connection,
memory, spectator UI, replays and rankings are shared by all games.

**State of the build:** roadmap step 1.4. The engine runs complete matches of
any plugin, stores their event logs in Postgres and rebuilds the state from a
log. A seat is played by a random bot or by the agent runner, which prompts a
model and reads its answer; in tests and CI that model is the mock LLM. The
LiteLLM wrapper for real models exists, but nothing starts a match with it yet:
`config/models.yaml` is empty until the cost caps land (step 1.5). There is one
playable game, High Card (`games/toy`). The arena API exposes
`GET /health` (it migrates the database at startup) and the Werewolf setup
endpoints, the worker is a heartbeat placeholder, the web UI (`web/`,
SvelteKit) has a home page and placeholders for the other pages. Sections below
marked *not built yet* describe the target from the spec and get filled in as
their phase lands.

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
   observation, the tools allowed now, and every event they were allowed to
   see so far. In a simultaneous game all active players decide on the same
   state.
2. The agent answers with a `Reply`: one `Action`, or a `problem` when its
   model gave no usable tool call, and optionally a `thought`. The engine logs
   the thought for spectators only.
3. The engine checks the action: the tool name, then the arguments against the
   tool's JSON Schema, then the plugin's `validate`. A rejected answer goes
   back with a clear error, up to 2 corrections.
4. If there is still no legal action, the game's `random_action` plays and the
   log says why (`action_fallback` with a `reason`): `rejected` after the last
   correction, `timeout` when the turn took longer than `turn_timeout` (60 s by
   default, corrections included), `agent_failed` for a seat whose agent gave
   up (see below).
5. `apply_actions`, then `step`, let the plugin emit game events.
6. A turn without a game event is a plugin bug and stops the match.

Validation lives in the engine only. Agents never judge an action.

*Not built yet:* streaming to the UI (step 1.6).

### Agents

Anything with `async act(request) -> Reply` can take a seat (`Agent` in
`arena/engine/types.py`). There are two:

- `RandomBot` (`arena/agents/random_bot.py`) plays the game's `random_action`.
- `ModelAgent` (`arena/agents/runner.py`) is the agent runner. Per request it
  builds the prompt (`prompt.py`), calls its model, and reads the answer: plain
  text is the private thought, the first tool call is the action.

`ModelAgent` talks to its model through one function, the `ModelCall`
(`arena/agents/model.py`): messages and tool schemas in, text and raw tool
calls out, `ModelError` on failure. Two things implement it:

- `MockLLM` (`mock_llm.py`) plays a script: fixed answers, functions that
  answer from the prompt, `ModelError`s, or `HANGS`. Everything on the arena
  side of the boundary, prompt building, parsing, retries and the engine, runs
  for real against it. Use it for every test and every local match:

  ```python
  plugin = ToyGame()
  mock = MockLLM(ModelError("RateLimitError"), tool_call("play_card", {"card": 3}))
  match = Match(plugin, {"p1": ModelAgent(mock, plugin), ...}, seed=1)
  ```

  `mock.calls` holds every prompt it was sent. `tests/agents/` shows the
  patterns, including a mock that reads its hand from the prompt.
- `LiteLLMModel` (`litellm_model.py`) calls a real model. It is the only code
  that can spend money. Never use it in tests or CI. It imports LiteLLM on
  first use, in LiteLLM's offline mode, because the import is slow and would
  otherwise download a price list.

Failures:

- A failed model call is retried 3 times, after 1, 2 and 4 seconds. Errors
  that a retry cannot fix (bad key, bad request) are not retried.
- When the retries are used up, `ModelAgent` raises `AgentError`. The engine
  logs `agent_failed` (spectators only) and plays random legal actions for
  that seat until the match ends; the agent is not asked again.
- A turn that runs out of time costs only that turn. The model is asked again
  on its next turn.
- Logs and events carry only the kind of failure (the error class name), never
  a prompt, a key or a provider message.

### Prompts

The system message is what the server says: who the player is, the game's
`rules.md`, how to answer. The user message is game data: the observation in
`<situation>`, the last 40 visible events in `<events>`, then the ask (with
the server's error on a correction).

- A prompt is built only from the `TurnRequest`, and the engine fills that
  with events the player may see. Thoughts and other players' private events
  never get there.
- Game data is JSON, one event per line, with `<` escaped. Text from another
  model can therefore not start a line, close a block or pose as the server.
- Text a player wrote is a game event of type `message` with exactly
  `{"player", "text"}` (`MESSAGE` in `arena/engine/types.py`; the engine
  rejects any other shape). The prompt shows it as `player p2 says: "..."`,
  the reader's own as `you said: "..."`.

### Events and state

A match is a list of `Event`s. Engine events (`match_started`, `thought`,
`action_accepted`, `action_rejected`, `action_fallback`, `agent_failed`,
`match_finished`) are bookkeeping. Game events come from the plugin through
`ctx.emit` and are the only thing that changes the game state: `emit` records
the event and passes it to the plugin's `apply_event` at once. Replaying the
game events over `initial_state` therefore rebuilds the exact state.

Every event says who may see it: `visible_to=None` is public, a list of
players is private to them, an empty list is spectators only. The seed,
thoughts and `agent_failed` are spectators only; a player's attempts are
visible to that player.

Whatever an agent writes is made storable before it is logged: NUL characters
and broken Unicode are dropped, NaN and infinity become null.

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
  ratings/      multiplayer Elo, statistics, profile and rating store
  worker.py     match worker process
games/          one package per game: plugin.py, rules.md, data, tests/
  toy/          High Card, the reference plugin
  liars_deck/   Liar's Deck: the bluff card game (plugin, variants, rules.md)
  poker/        No-Limit Hold'em tournament: cards, evaluator, betting, plugin
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

Web UI (`web/`, Node 24):

```bash
cd web && npm ci              # install from package-lock.json
npm run dev                   # dev server; reads ARENA_API_URL (default http://127.0.0.1:8100)
npm run lint                  # prettier + svelte-check
npm run test:unit             # vitest
npx playwright test           # smoke tests on 3100 (WEB_URL overrides); needs demo_seed data
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

1. Create `games/<id>/` with `__init__.py`, `plugin.py`, `rules.md` and
   `tests/`. `rules.md` is the English rule summary models get in their
   prompt: short and complete. The prompt puts the game's `name` above it, so
   the text does not need the title.
2. Define the state as a Pydantic model and subclass `GamePlugin`
   (`arena/engine/plugin.py`). Set `id`, `name`, `version`, `min_players`,
   `max_players` and `turn_mode`. `name` is the title people and models read,
   and the only place where it is written.
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
7. If players can talk, emit their words as
   `ctx.emit(MESSAGE, {"player": author, "text": words}, visible_to=...)` and
   put player-written text in no other event.
8. Tests, as in `games/toy/tests/`: full bot matches for every player count,
   same seed gives the same events and state, observations do not depend on
   other players' hidden information, private events are private, rejected
   actions carry a useful message. Add a match with mock-LLM players, as in
   `tests/agents/test_model_match.py`.

*Not built yet:* the registry that finds games by id (step 1.6), and what the
UI needs to draw a game (phase 5).

### A Werewolf role

One YAML file in `games/werewolf/roles/<id>.yaml`; the id is snake_case English
and equals the file name. Fields, checked by
`games/werewolf/roles/role.schema.json`: `id`, `name` (German display name),
`team` (`village`, `wolves`, `solo`), `unique`, `weight` (integer),
`night_order` (integer or `null`), optional `first_night_only`, `hooks`
(hook name to handler name), `description` and `rules_snippet` (1-3 sentences
that go into the prompt when the role is in play).
`games/werewolf/roles/README.md` has the night order.

```bash
uv run pytest games/werewolf   # schema check of every role and template
```

To make the role selectable in a template, add it to
`games/werewolf/templates.yaml`; the test checks that the template stays
fillable (counts, unique roles, wolves below half). Today nothing loads the
roles at startup; the test is the check. A new ability needs a handler in code
(planned, phase 4); a role without new abilities needs none.

### A Werewolf template or option

`games/werewolf/templates.yaml` (role counts per template, `fill` for villagers)
and `games/werewolf/options.yaml` (captain, role visibility). Same test command.

### A personality

One YAML file in `config/personalities/<id>.yaml`, checked against
`config/personalities/personality.schema.json`: `id`, `name`, `description`,
`values` (`risk_taking`, `honesty`, `aggression`, integers 0-100) and
`speech_style`.

```bash
uv run pytest tests/config
```

### A Liar's Deck variant

One YAML file in
`games/liars_deck/variants/<id>.yaml`, validated by `games/liars_deck/variants.py`
(`load_variant`, `load_variants`; errors name file and field), and played by
`games/liars_deck/plugin.py` (`settings={"variant": "<id>"}`). The schema file
`variants/variant.schema.json` is generated from the models:

```bash
uv run python -m games.liars_deck.variants   # regenerate the schema
uv run pytest games/liars_deck
```

A new Werewolf role already shows up in the role selection
(`games/werewolf/selection.py`, served at `GET /games/werewolf/roles` and
`POST /games/werewolf/selection/validate`): give it a `team`, `unique` and a
balance `weight`.

### A unit, building or event

An entry in `games/civ/data/units.yaml` or `buildings.yaml`, or a new file in
`games/civ/data/events/`; no code. `games/civ/data/README.md` lists the fields;
`uv run python -m games.civ.data_loader` checks the result. The systems that
use the data land in phase 7.

### A system

*Not built yet: phase 7.* Target: a module that registers its tools and hooks
into engine events such as `on_turn_start` and `on_turn_end`.
