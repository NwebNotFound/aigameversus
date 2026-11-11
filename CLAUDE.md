# CLAUDE.md

Guide for anyone, human or AI, who continues this project. Read it together
with [docs/DESIGN.md](docs/DESIGN.md) (the spec, German) and
[docs/DECISIONS.md](docs/DECISIONS.md) (where the spec is open or overridden;
it wins over the spec).

## What this is

AIGameVersus is an arena, not a single game. AI models play turn-based games
against each other; humans watch. Each game is a plugin. Model connection,
memory, spectator UI, replays and rankings are shared by all games.

**State of the build:** phases 1 to 6 are built (platform, Liar's Deck, Poker, Werewolf,
spectator UI, profiles with statistics and trust); the Throne of Tokens match (phase 7)
is not playable yet. The engine runs
complete matches of any plugin, stores their event logs in Postgres and
rebuilds the state from a log. A seat is played by a random bot or by the
agent runner, which prompts a model and reads its answer; in tests and CI that
model is the mock LLM. Model calls are counted against cost caps, and a match
pauses at a cap.
`config/models.yaml` lists the caps and a roster of real models. The `arena`
command (`--models`) and `POST /matches` (`models`, on a server started with
`ARENA_ALLOW_MODEL_SEATS=1`) can seat them, paid calls inside the caps. Four games can
be played: High Card (`games/toy`), the reference plugin, Liar's Deck
(`games/liars_deck`), Poker (`games/poker`) and Werewolf (`games/werewolf`). The arena API starts bot
matches, lists, controls and streams them over WebSocket, next to
`GET /health` (it migrates the database at startup), the leaderboard, player
profiles with their game statistics (`GET /profiles/{id}/stats`), the
Werewolf setup endpoints and `GET /setup` (models, personalities and cost
caps for the form). The worker is a heartbeat placeholder, the web UI
(`web/`, SvelteKit) has a home page, the leaderboard, player profiles and the
new-match form (`/matches/new`), the live view of a match (`/matches/<id>`)
and replays (`/replays`, `/replays/<id>`).
Sections below marked *not built yet* describe the target from the spec and
get filled in as their phase lands.

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
6. A turn without a game event is a plugin bug and stops the match. So does a
   match that is still not over after the game's `max_turns` turns (or the
   `max_turns` given to this `Match`): the engine logs `turn_limit_reached`
   and raises `PluginError`, so a game that never ends cannot play, store and
   bill forever.

Validation lives in the engine only. Agents never judge an action.

An agent can also raise `MatchPaused` instead of answering: the match cannot
go on without the user (today: a cost cap, see below). The engine then cancels
the other players of the turn, drops the turn, logs `match_paused` and lets
`Match.run()` raise the pause. Calling `run()` again logs `match_resumed` and
plays that turn from its start, so a paused game continues exactly as it would
have without the pause.

### Running matches

Three ways:

- `arena run --game toy --bots` (`arena/cli.py`) plays a match in its own
  process and prints every event. It needs no server and no database, and
  stores nothing. `arena games` lists the games.
- `arena run --game liars_deck --models glm-flash,deepseek-flash,...` seats
  models from `config/models.yaml`, one per seat in that order. **This makes
  paid model calls**, like model seats in `POST /matches` (below).
  Every call goes through one `Budget` (see Cost caps), so the command needs
  `DATABASE_URL` for the ledger; it applies the migrations, records the match
  in `matches` and stores its events like the API does. The provider's key
  comes from the environment (`KEY_VARIABLES` in `arena/config.py` names the
  variable per provider); without it the command refuses to start, before
  anything is booked. After the events it prints the result, what
  each seat cost, and whether the stored log rebuilds the final state;
  `--save FILE` writes seats, result, cost and all events as JSON. Nobody is
  there to allow more money, so a cost cap ends the match: it is closed as
  `interrupted` and the command exits with 3 (1 if the replay differs).
- `POST /matches` (`arena/api/matches.py`) starts a match as a task inside the
  API process (`arena/api/live.py`). Its record is a row in `matches`
  (`running`, `finished`, `failed`, `aborted` by a spectator, or
  `interrupted` when the server stopped under it), its events go to the event
  store turn by turn.
  `WS /matches/{id}/events` sends the log from its first event, one JSON object
  per event with its position `seq`, waits for further turns while the match
  runs and closes when it stops; a finished match is sent in one go.
  `GET /matches/{id}/events` returns the same log as a list. `turn_delay` in
  the request makes the match wait between turns so that people can follow.
  The server plays at most 10 matches at a time (`MAX_RUNNING`) and answers
  429 to a start beyond that; a match that never ends stops at its turn limit
  and is marked `failed`.
  With `"models": ["glm-flash", ...]` (one per seat) and `"confirm_spend":
  true` the seats are models behind one `Budget`, as with the command. Model
  seats are refused (403) unless the server runs with
  `ARENA_ALLOW_MODEL_SEATS=1`, and (503) without the provider's key or its
  ledger (see Cost caps); a cap ends the match as `interrupted`. Model
  matches are not rated yet: the API rates bot matches only, until the model
  profiles (one per model and personality) reach it. Every match record has `seats` (seat ->
  `{name, model_id, kind}`; the name is `name` in `config/models.yaml`, else
  the id; bots are "Random Bot pN") and `origin` (`played` or `imported`);
  `GET /replays` adds `real`.
- A running match can be paused, resumed, sped up or slowed down and aborted:
  `POST /matches/{id}/pause`, `/resume`, `/abort`, `PUT /matches/{id}/speed`,
  state in `GET /matches/{id}/control`. A pause takes effect between turns,
  so no agent is asked while a match is paused. `GET /matches/{id}/board`
  returns the game's `render_spec` after the stored turns and
  `GET /matches/{id}/cost` what its model calls cost per player.

The API shows a match as a spectator sees it, thoughts and hidden cards
included. It has no authentication and listens on localhost only.

Games are found by folder (`arena/games.py`): `games/<id>/plugin.py` with one
`GamePlugin` class whose `id` is the folder name. A folder without `plugin.py`
is data for a game that is not written yet; a folder that breaks the rule
stops the start.

### Agents

Anything with `async act(request) -> Reply` can take a seat (`Agent` in
`arena/engine/types.py`). There are two:

- `RandomBot` (`arena/agents/random_bot.py`) plays the game's `random_action`.
- `ModelAgent` (`arena/agents/runner.py`) is the agent runner. Per request it
  builds the prompt (`prompt.py`), calls its model, and reads the answer: the
  first tool call is the action, and its `thought` argument is the private
  thought. `tool_schemas` adds that argument to every tool and the runner
  takes it out again, so a game never sees it and no game tool may use the
  name. Text beside the call counts as the thought when the argument is empty.

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
  that can spend money, and matches get it only through `Budget.model`, which
  counts every call (see Cost caps). Never use it in tests or CI. It imports
  LiteLLM on first use, in LiteLLM's offline mode, because the import is slow
  and would otherwise download a price list, and it switches LiteLLM's own
  logger off, because that logs whole requests and provider error texts.

What the first matches with real models taught (four and six cheap models;
in the first, 83 of 130 answers were rejected):

- Reasoning models think before they answer, the thinking is billed as output,
  and it counts against `max_output_tokens`. Two of four spent the whole limit
  thinking and never reached their tool call. `limits.reasoning_effort` in
  `config/models.yaml` (`low`) is sent with every call and keeps it short.
- Left free, several models answer in prose or write the call as text
  (`[raise(amount=40)]`, `default_api.call_liar(...)`). Every call is sent
  with `tool_choice: required`, and the thought has its place inside the call,
  because many models cannot write text and call a tool in one answer.
- An answer that ran into the output limit is marked (`ModelReply.cut_off`).
  If it has no tool call, the player is told that it was cut off and to be
  brief, not just that the tool call is missing.
- A model that only reasoned has its reasoning as its text.
- One model name can stand for several providers, and not every provider
  takes every option: the same model answered one match and refused the next
  request (400). A request refused with the options (`tool_choice`,
  `reasoning_effort`) is sent once more without them before the seat is
  given up; a refused request is not billed.

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

### Cost caps

`config/models.yaml` holds the limits (0.50 € per match, 25 € per calendar
month, token limits per call, how long reasoning models may think) and the
models with their prices.
`arena/config.py` loads and checks it.

A match that uses models gets one `Budget` (`arena/agents/budget.py`), and
every model call of the match is wrapped by it:

```python
budget = Budget(Ledger(pool), match_id, load_config())
agent = ModelAgent(budget.model("p1", "deepseek-flash"), plugin)  # a real model
agent = ModelAgent(budget.meter("p1", "deepseek-flash", mock), plugin)  # a mock at its prices
```

- Before a call is sent, it is booked in the ledger (`arena/db/ledger.py`,
  table `model_calls`) at the most it can cost: request size in bytes as input
  tokens, the output limit as output tokens. When the answer reports its
  tokens, the booking is corrected. A call that reports nothing (error,
  timeout, crash) keeps the upper bound, so the ledger is never too low.
  The caps hold as long as a provider bills no more than that bound; if one
  does, the real cost is booked and the next call pauses.
- If the booking would take the match or the month past its cap, the call is
  not sent and the budget raises `MatchPaused("match_cap" | "month_cap")` with
  the amounts. The match pauses as described under One turn. To continue,
  whoever runs the match asks the user, sets a higher `budget.match_cap` or
  `budget.month_cap` and calls `run()` again.
- Money is an integer: millionths of a euro (`*_micro_eur`), rounded up per
  call. Prices in the file are US dollars per million tokens; `usd_to_eur`
  converts.
- A request that could be longer than `max_input_tokens` is not sent; that
  seat fails (`PromptTooLong`) and the random bot takes it.
- The ledger is the table `model_calls` in `LEDGER_DATABASE_URL`, by default
  the match database (`arena/db/database.py`, `ledger_url`). The stack keeps
  it in a Postgres of its own that outlives `docker compose down -v`
  ([docs/COSTS.md](docs/COSTS.md)); `scripts/backup-ledger.sh` dumps it.
- Without a ledger there is no model call. Before a model match starts, the
  API and the command call `Ledger.check`: a ledger that does not answer, or
  is empty while the match database holds finished model matches played
  here, not imported (the wrong one, or a lost one), refuses the match with `LedgerUnavailable` (503 in the
  API), and nothing is recorded or booked. The server itself starts without
  its ledger, so bot matches play on; `/matches/{id}/cost` answers 503 and
  `/replays` shows the costs as null until the ledger answers.
- The API key comes from `OPENROUTER_API_KEY`, or from the file that
  `OPENROUTER_API_KEY_FILE` names (the stack mounts it read-only, see
  `docker-compose.models.yml`). `load_keys` in `arena/config.py` reads the
  file at every start of a model match and puts the key into the environment,
  where LiteLLM reads it. It is in no config file, log, event or database row.

### Prompts

The system message is what the server says: who the player is, the game's
rules (`rules.md`), how to answer. The user message is game data: the game's
summary of the turn in `<summary>` if it has one, the observation in
`<situation>`, the last 40 visible events in `<events>`, then the ask (with
the server's error on a correction).

- A game can have prompt versions, chosen per match by its settings
  (Liar's Deck, Poker and Werewolf: `prompt_version` `<game>-p1`, the default and the
  prompt as it was, or `<game>-p2`). `ModelAgent(call, plugin,
  settings=...)` asks the plugin for `rules(settings)` once and for
  `situation_summary(observation, settings)` on every turn; the API and the
  command pass the match settings. `prompt_version(settings)` is recorded in
  `match_started`, in the match record (`prompt_version` in `GET /matches`
  and `/replays`) and in the `--save` export, so an analysis can tell the
  versions apart. A game without versions inherits `"v1"`, `rules.md` and no
  summary, and its prompt is byte for byte what it was.
- A summary is built from the player's observation only, so it can never
  hold what the player may not see; its `<` is escaped like all game data.
- The player's seat is named three times: at the top of the system message
  ("wherever the game data names p8, that is you"), in the ask at the end
  ("You are p8."), and on every event the player did, which starts with
  `[you]` (the doer is the event's `player`, `caller` or `from`:
  `ACTOR_FIELDS` in `arena/agents/prompt.py`; add a game's field there). In the first real Werewolf match a model argued against its own
  claim and voted for itself; it had read its seat once, far above.
- A prompt is built only from the `TurnRequest`, and the engine fills that
  with events the player may see. Thoughts and other players' private events
  never get there.
- Game data is JSON, one event per line, with `<` escaped. Text from another
  model can therefore not start a line, close a block or pose as the server.
- Text a player wrote is a game event of type `message` with exactly
  `{"player", "text"}` (`MESSAGE` in `arena/engine/types.py`; the engine
  rejects any other shape). The prompt shows it as `player p2 says: "..."`,
  the reader's own as `you said: "..."`.

Game side of a prompt version: a game offers `<game>-p1` (its `rules.md`, as it
was) and `<game>-p2` (`rules_v2.md` plus a situation summary) by overriding
`prompt_version(settings)`, `rules(settings)` and `situation_summary(observation,
settings)` (None for p1); `games/poker/prompt.py` is the pattern. Every tool a
turn can offer must be named as `` `tool(` `` in the p2 rules (a test checks it),
and `games/<game>/tests/golden/` holds the exact prompt text per version
(`UPDATE_GOLDEN=1` rewrites it).

### Events and state

A match is a list of `Event`s. Engine events (`match_started`, `thought`,
`action_accepted`, `action_rejected`, `action_fallback`, `agent_failed`,
`match_paused`, `match_resumed`, `turn_limit_reached`, `match_finished`) are
bookkeeping. Game events come from the plugin through `ctx.emit` and are the
only thing that changes the game state: `emit` records the event and passes it
to the plugin's `apply_event` at once. Replaying the game events over
`initial_state` therefore rebuilds the exact state.

Every event says who may see it: `visible_to=None` is public, a list of
players is private to them, an empty list is spectators only. The seed,
thoughts, `agent_failed` and pauses are spectators only; a player's attempts
are visible to that player.

Whatever an agent writes is made storable before it is logged: NUL characters
and broken Unicode are dropped, NaN and infinity become null.

Event data must be plain JSON (lists, not tuples; string keys), because a
stored event has to come back exactly as it was applied. The engine stops a
match that emits anything else. Never read anything from the order of keys in
event data: Postgres stores a JSON object without it. Where order matters, use
a list. `tests/test_games.py` replays a bot match of every game with the keys
reversed.

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
   LLM. Real model calls stay behind the cost caps: build a real model only
   with `Budget.model`.
9. **No secrets anywhere** except a local `.env`. Not in code, logs, tests,
   screenshots, commits or PR text.
10. **Original assets only.** No names, characters or art from existing games.
    Every asset is listed in `docs/CREDITS.md`.

## Layout

```
arena/
  api/          FastAPI app: matches and their event stream, leaderboard, setup
  engine/       turn loop, plugin interface, seeded RNG, event log
  agents/       agent runner, prompts, model calls, mock LLM
  memory/       profiles and the three memory layers
  gamemaster/   match setup, scheduling, narrator
  db/           connection pool, SQL migrations, event store, spend ledger
  ratings/      multiplayer Elo, statistics, profile and rating store
  chronicle/    the chronicler: a finished match as a story (templates, styles, languages)
  transcript/   the one readable play-by-play of a match: a renderer per game, de and en
  cli.py        the `arena` command
  config.py     loader of config/models.yaml (limits, models, prices)
  games.py      finds the games under games/
  worker.py     match worker process
games/          one package per game: plugin.py, rules.md, data, tests/
  toy/          High Card, the reference plugin
  liars_deck/   Liar's Deck: the bluff card game (plugin, variants, rules.md)
  poker/        No-Limit Hold'em tournament: cards, evaluator, betting, plugin
  werewolf/     Werewolf: plugin, abilities, roles, templates, selection
  civ/          Throne of Tokens, in parts: data, map, fog of war, economy, armies
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
# Real models in the stack: COSTS MONEY. Key file and ledger first: docs/COSTS.md
docker compose -f docker-compose.yml -f docker-compose.models.yml up -d --build
docker compose down           # stop it (--volumes also deletes the database)
uv run arena games            # the games that can be played
uv run arena run --game toy --bots --seed 7   # a bot match in the terminal
# Real models: COSTS MONEY (inside the caps). Needs DATABASE_URL and OPENROUTER_API_KEY.
uv run arena run --game liars_deck --models glm-flash,deepseek-flash --save match.json
```

The same in the running stack, and a match through the API:

```bash
docker compose exec arena arena run --game toy --bots
curl -X POST http://127.0.0.1:8100/matches -H "content-type: application/json" \
  -d '{"game": "toy", "turn_delay": 1}'
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
   the text does not need the title. For a second prompt version, override
   `prompt_version`, `rules` and `situation_summary` (see `games/poker/prompt.py`).
2. Define the state as a Pydantic model and subclass `GamePlugin`
   (`arena/engine/plugin.py`), once, in `plugin.py`. Set `id` (the folder
   name), `name`, `version`, `min_players`, `max_players`, `turn_mode` and
   `max_turns`: the most turns a match can take under the rules, with room to
   spare (the default is 10 000). A turn is one round of asking the active
   players. The class must be creatable without arguments. That is all the
   registration there is: `arena games` and `GET /games` then list the game.
   `name` is the title people and models read, and the only place where it is
   written.
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
8. A renderer for the transcript, `arena/transcript/<id>.py`: a class with one
   `handle_<event type>` method per event the plugin emits (and register it in
   `RENDERERS`). It returns a line in English and German, an importance (1
   bookkeeping, 2 normal, 3 highlight) and a kind; a test fails when a plugin
   emits an event type that has no method. The CLI, the API, the live view,
   replays and exports all show these lines; do not write a second formatter.
9. Tests, as in `games/toy/tests/`: full bot matches for every player count,
   same seed gives the same events and state, observations do not depend on
   other players' hidden information, private events are private, rejected
   actions carry a useful message. Add a match with mock-LLM players, as in
   `tests/agents/test_model_match.py`.

What the UI draws comes from the plugin's `render_spec(state)`, a plain JSON
dict with a `layout` (`card_table`, `poker_table`, `player_circle`) and a list
of `seats`, each with a `player`. Until a game has its own table in `web/`,
the generic board shows the other fields as text; it hides the fields `hand`,
`cards` and `role` in the spoiler-free view. A spoiler-free page gets its board
through an allowlist per layout in `web/src/lib/server/redact.ts`: a new layout
or field shows nothing there until it is listed as public. A game without
`render_spec` shows its events only.

### A model

An entry under `models` in `config/models.yaml`: an id of your choice,
`provider` (only `openrouter` today), `model` (the provider's name for it) and
the prices `input_usd_per_mtok` and `output_usd_per_mtok` in US dollars per
million tokens, as the provider lists them. The cost caps count with these
numbers, so check them against the provider's price page, and pick models that
support tool calls. No code.

```bash
uv run pytest tests/test_config.py   # validates the file
```

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
roles at startup; the test is the check. A new ability needs a handler in
`games/werewolf/abilities.py` (a `NightAbility` in `NIGHT`, or a passive hook
the plugin handles by name); the plugin refuses a role whose handlers are
missing. A role without new abilities needs none.

### A Werewolf template or option

`games/werewolf/templates.yaml` (role counts per template, `fill` for villagers)
and `games/werewolf/options.yaml` (captain, role visibility). Same test command.

### A trust rule

After every rated match the server turns what each player saw into facts
(`arena/memory/facts.py`, one extractor per game) and the facts into trust
between profiles (-100 to +100, clamped) with a short note each
(`arena/memory/store.py`, once per match id). How much a fact is worth, and its
note, is data: `config/memory/trust.yaml`. A fact is read only from the events
its observer could see, so it never carries another player's secret. A new kind
of fact needs its extractor case, its name in `KINDS` and a rule in the file;
the loader refuses a fact without a rule and a rule without a fact.

```bash
uv run pytest tests/memory
```

Each remembered match also leaves every seated profile a one-line summary from
its own view (`arena/memory/summary.py`, a template; a `Summarizer` can replace
it). Before a match, `memory_block(store, profile, opponents)`
(`arena/memory/block.py`) builds what a model remembers of the opponents at
the table, at most `MEMORY_CHARS` long, and `ModelAgent(..., memory=block)` puts
it in the prompt inside `<memory>`, marked as data. `"memory": false` in
`POST /matches` plays a fair benchmark that reads and writes nothing;
`arena memory reset [--profile ID] --yes` and `POST /memory/reset` forget
(ratings stay).

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
(`games/werewolf/selection.py`, served at `GET /games/werewolf/roles`,
`GET /games/werewolf/templates?players=N` and
`POST /games/werewolf/selection/validate`, and shown in the new-match form): give it a `team`, `unique` and a
balance `weight`.

### A unit, building or event

An entry in `games/civ/data/units.yaml` or `buildings.yaml`, or a new file in
`games/civ/data/events/`; no code. `games/civ/data/README.md` lists the fields;
`uv run python -m games.civ.data_loader` checks the result. A building's cost,
yields and the other fields the economy reads work at once; the README says
which effects still wait for their system.

### The Throne of Tokens map

The game is built in parts (roadmap steps 7.1 to 7.3 so far; there is no
plugin yet, so `arena games` does not list it). The map:

- `games/civ/world.py`: `generate_map(players, data, rng)` returns a
  `WorldMap`: rows of terrain ids and one `Start` per nation. A tile is
  `(col, row)`; odd rows sit half a tile to the right. `distance(a, b)` counts
  steps, `world.within(tile, radius)` lists the tiles around one.
- `games/civ/fog.py`: `visible_tiles(world, viewpoints)` and
  `map_view(world, visible)`, the map with `None` for what a nation does not
  see. An observation must be built from the view, never from the map.

The size of the map, the terrain mix, the rare tiles and the tiles around a
capital are numbers under `map` in `games/civ/data/balance.yaml`; the README
next to it says what each does and what the generator guarantees.

### The Throne of Tokens economy and armies

- `games/civ/state.py`: `CivState` holds the round number, the map, one
  `Nation` per player (its stock of the four resources, its count of hungry
  rounds), the cities in founding order and the armies. `new_game(players,
  data)` is the state before the map is drawn. Later steps add their part of
  the state here.
- `games/civ/economy.py`: the rules of cities. Questions about the state
  (`city_yields`, `worked_tiles`, `building_slots`, `city_viewpoints` for the
  fog, `upkeep`, `units_lost_to_hunger`), orders with a check each
  (`build_problem` and `build`, `demolish_problem` and `demolish`,
  `focus_problem` and `set_focus`; `found_city`) and the steps of a round
  (`finish_construction`, `produce`, `grow`).
- `games/civ/armies.py`: the rules of armies. Questions (`movement`,
  `reachable`, `training_cost`, `army_viewpoints`), orders with a check each
  (`train`, `move`, `split`, `merge`, `disband`, `settle`),
  `deploy_start_units` for the setup and the round step `starve`.
- `games/civ/turn.py`: `begin_round`, and `apply_event`, the one function
  through which every event changes the state. Its docstring has the order
  of the steps of a round.

How these follow the engine's rules, and what the next systems should copy:

- A function that changes something takes the `TurnContext` and emits events;
  only the functions in a module's `APPLIERS` touch the state, and
  `turn.apply_event` routes each event to its applier. The plugin (step 7.6)
  passes its context through and calls `turn.apply_event`.
- An event carries the outcome (the cost paid, the new stock, the path
  walked, which units were lost), so applying it reads no game data. Every
  event except `round_started` is private to the nation it concerns: what
  others learn about a city or an army comes from their fog view.
- A `*_problem` function returns `None` or a message for the player. The
  order itself raises `ValueError` when it is not legal, so whoever resolves
  a round checks each order again at that moment: trades and other orders
  come first and may have used up what it needs.
- Randomness: `ctx.rng("hunger", state.round, player)`. Every stream name
  carries the round, because a stream can be asked for once per match.
- "Once per round" is kept in the state, not left to the caller: an army
  remembers the round of its last move, units split off from it and an army
  it is merged into inherit that, and `move_problem` refuses a second move.
  Do the same for any later rule of this kind.
- A new system: a module with its functions and `APPLIERS`, its part of the
  state in `state.py`, one line in `turn.py`. Tests drive it through `Realm`
  in `games/civ/tests/realm.py`, which is as strict as the engine about
  random streams and event data; `games/civ/tests/test_sessions.py` plays
  random legal orders of all systems and should learn the new orders.

### A system

*Not built yet: phase 7.* Target: a module that registers its tools and hooks
into engine events such as `on_turn_start` and `on_turn_end`.
