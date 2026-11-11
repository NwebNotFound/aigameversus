# Decisions

Decisions taken where [DESIGN.md](DESIGN.md) is open, or where this project
deliberately differs from it. `DESIGN.md` is kept as the original spec, apart
from the author line and the game title (D-018); where the two disagree, this
file wins.

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

## D-009 · Plugins change state only through events

- **Date:** 2026-11-11
- **Decision:** The plugin interface differs from the sketch in the spec.
  `setup`, `apply_actions` and `step` get a context and call `ctx.emit(...)`
  instead of returning events; the engine passes every emitted event to a new
  method `apply_event`, the only place where a plugin may mutate its state.
  `initial_state` (pure, no randomness) replaces the state-building half of the
  spec's `setup`. `validate` returns `None` or an error message. `random_action`
  is part of the interface. `render_spec` is left out until the UI defines what
  it needs (phase 5).
- **Why:** If state changes only by applying events, the event log is complete
  by construction: replay is a fold over the log, needs no seed and no rule
  logic, and keeps working for old logs after rules change. Emitting and
  applying in one call means a plugin writes each state change once and can
  read the updated state right away.
- **Alternatives:** Mutating in `apply_actions` and returning descriptive
  events (the log may then silently miss state); storing only actions and
  re-running the rules for replay (breaks old replays when rules change).

## D-010 · Named random streams derived from the seed

- **Date:** 2026-11-11
- **Decision:** A plugin gets randomness from `ctx.rng(*key)`, a stream derived
  from the match seed and the key by SHA-256. A key may be used once per match.
  Random bots and the engine fallback use separate streams.
- **Why:** A stream depends only on seed and key, so a match can continue from
  its log without saved generator state, rejected attempts and bot draws cannot
  shift the game's randomness, and a game can deal the same cards again on
  purpose (duplicate poker: key by hand number).
- **Alternatives:** One generator for the whole match (its state must be saved
  to resume, and any extra draw changes everything after it).

## D-011 · Validation order and fallback

- **Date:** 2026-11-11
- **Decision:** The engine checks an action in three steps: the tool is offered
  now, the arguments match the tool's JSON Schema (`jsonschema`), the plugin's
  `validate` accepts it. A rejected action is returned with the error; after 2
  corrections the game's `random_action` plays instead and the log marks it
  with `action_fallback`. Every attempt is logged, visible only to that player
  and to spectators.
- **Why:** Generic checks give every game the same clear errors for malformed
  model output, and plugins validate only rules. A random legal move keeps the
  match going in every game without a per-game notion of "do nothing".
- **Alternatives:** A per-game default action; skipping the player's turn.

## D-012 · One engine loop for all turn modes, one action per request

- **Date:** 2026-11-11
- **Decision:** The loop is the same for `sequential`, `simultaneous` and
  `tick`: ask all active players at once, apply their actions together, then
  `step`. Sequential games may name at most one active player; tick games may
  name none. An agent returns one action per request; a turn with several
  actions (talk, then play) is the plugin keeping the player active. The engine
  is async. A turn that produces no game event stops the match as a plugin bug.
- **Why:** One code path to test. Async lets simultaneous players call their
  models in parallel later, while the log order stays the seat order.
- **Alternatives:** A loop per turn mode; batches of actions per request (may
  come with the agent runner if model calls need it).

## D-013 · High Card as a shipped reference game

- **Date:** 2026-11-11
- **Decision:** `games/toy` is a real plugin (a small trick-taking game), not a
  test fixture.
- **Why:** It is the game the CLI runs before a real game exists, and the
  template `CLAUDE.md` points to for adding a game.
- **Alternatives:** A fixture under `tests/` only.

## D-014 · asyncpg and SQL migration files, no ORM

- **Date:** 2026-11-11
- **Decision:** Postgres access uses asyncpg with plain SQL. Schema changes are
  numbered `.sql` files in `arena/db/migrations/`, applied in order inside one
  transaction and recorded in `schema_migrations`; an advisory lock keeps two
  processes from migrating at once. The arena applies them at startup.
- **Why:** The data model is an append-only event table plus a few lookup
  tables later; SQL says that more directly than an ORM mapping. The engine is
  async, so the driver is too. A migration runner of thirty lines is easier to
  read than an Alembic setup for forward-only migrations.
- **Alternatives:** SQLAlchemy with Alembic; psycopg 3 (its async mode needs a
  different event loop on Windows).

## D-015 · The log is stored once per turn, and replay is strict about versions

- **Date:** 2026-11-11
- **Decision:** A match hands its new events to the store after setup, after
  every completed turn and at the end, each batch in one transaction with
  explicit positions (`match_id`, `seq` is the primary key). `replay` refuses a
  log whose game id or plugin version differs from the plugin it is given.
- **Why:** A stored log then always ends at a turn boundary, so a crashed match
  can be replayed to a state the game really had, and a second writer for the
  same match fails instead of interleaving. A plugin of another version may
  apply old events differently; failing loudly beats a silently wrong state.
  The stored events themselves stay readable for any version.
- **Alternatives:** One write per event (a crash could cut a turn in half);
  replaying across versions and hoping.

## D-016 · Event data is plain JSON, enforced at emit

- **Date:** 2026-11-11
- **Decision:** The engine rejects a game event whose data would change in a
  JSON round trip (tuples, non-string keys) and stops the match with a plugin
  error.
- **Why:** The live state is built from the same events that are stored. If
  storage changed an event, a replay would differ from the match. Checking at
  emit finds this in every bot match, without a database.
- **Alternatives:** Normalising silently; finding it only in database tests.

## D-017 · Database tests use a real Postgres, one schema per test

- **Date:** 2026-11-11
- **Decision:** Tests under `tests/db/` connect to the Compose database on
  `127.0.0.1:5433` (or `ARENA_TEST_DATABASE_URL`), each in a fresh schema that
  is dropped afterwards. Without a reachable server they are skipped locally;
  with `CI` set they fail. CI starts Postgres as a service container.
- **Why:** The store is SQL, so only the real database proves it. Schemas keep
  tests independent of each other and of development data.
- **Alternatives:** Mocking the driver; an in-memory fake store; testcontainers.

## D-018 · The bluff card game is called Liar's Deck

- **Date:** 2026-11-11
- **Decision:** The game's public name is "Liar's Deck" everywhere: README, UI,
  docs, and the game id (`liars_deck`, package `games/liars_deck/`). The spec
  used the title of the commercial game that inspired it as a working title;
  `docs/DESIGN.md` was edited to the new name. Code refers to the game by its
  id, and the display name is defined in exactly one place, so a later rename
  is a one-line change.
- **Why:** Decided by the project owner. The project carries no title,
  characters or assets of an existing game.
- **Alternatives:** Keeping the working title; a different title, which
  remains possible because of the single definition.

## D-019 · An agent answers with one action and a thought; thoughts are an engine channel

- **Date:** 2026-11-11
- **Decision:** `Agent.act` returns a `Reply`: exactly one `Action`, or a
  `problem` when there is no usable action (a model that only talked, or sent
  arguments that are not JSON), plus an optional `thought`. The engine records
  a thought as the engine event `thought` with `visible_to=()`: spectators
  only, not even its author gets it back. A `problem` is treated like any
  rejected action: logged, returned as the error, counted as a correction.
  Still one action per request (D-012); of several tool calls in one answer
  the first counts. Messages to other players are game tools, not a third
  field of the reply.
- **Why:** Thoughts exist in every game and must never leak, so one place in
  the engine handles them instead of one tool per plugin, and a plugin cannot
  get their visibility wrong. A model does not need its old thoughts back to
  play, and never feeding them into a prompt removes the path by which they
  could reach another player. Keeping "no action" inside the reply keeps the
  correction loop in the engine, the only place that validates.
- **Alternatives:** A `think` tool per plugin; thoughts visible to their
  author; an exception for unusable answers (the thought of that answer would
  be lost); a batch of actions per reply.

## D-020 · The turn clock is in the engine, and an agent that gives up loses its seat

- **Date:** 2026-11-11
- **Decision:** `Match(turn_timeout=60)` limits one turn of one player,
  corrections included. When the time is up, the answer is abandoned and the
  game's `random_action` plays. That costs only this turn; the agent is asked
  again on its next one. An agent that raises `AgentError` is out for the rest
  of the match: the engine logs `agent_failed` once (spectators only) and
  plays random legal actions for the seat without asking again. Every
  `action_fallback` carries a `reason`: `rejected`, `timeout` or
  `agent_failed`.
- **Why:** The engine already owns the fallback and the log, and a clock there
  covers every kind of agent. Per turn rather than per call, because
  spectators wait for turns. Replacing a dead model by random play keeps the
  match and its log complete, which a match with eight players needs more than
  it needs that one seat to play well. Other players are not told: they could
  not tell a human table mate's reason for playing badly either.
- **Alternatives:** A clock per model call inside the runner; skipping the
  turn of a slow player (needs a "do nothing" in every game); ending the match
  when a model fails; counting timeouts towards losing the seat.

## D-021 · One model-call boundary; the runner retries; the mock LLM stands behind it

- **Date:** 2026-11-11
- **Decision:** The agent runner (`ModelAgent`) reaches its model only through
  a `ModelCall`: messages and tool schemas in, text and raw tool calls out,
  `ModelError(reason, retryable)` on failure. `MockLLM` and `LiteLLMModel`
  implement it. The runner retries a failed call 3 times with pauses of 1, 2
  and 4 seconds; a failure marked as not retryable (wrong key, bad request) is
  not retried. When that is used up, the model counts as failed for good: the
  runner raises `AgentError` and the engine takes the seat (D-020). LiteLLM's
  own retries are switched off. `LiteLLMModel` imports LiteLLM on first use
  and in LiteLLM's offline mode; it maps a failure to its class name and drops
  the provider's message.
- **Why:** With the mock at the boundary, prompt building, answer parsing,
  retries and the engine run for real in tests, at no cost. One retry policy
  in one place can be tested with a fake sleep. Seven seconds of patience
  cover a rate limit or a dropped connection; a longer outage would stall
  every turn of that seat, so the seat is handed over once instead. Importing
  LiteLLM takes seconds and downloads a price list unless offline mode is set,
  which no test, CLI start or bot match should pay for. Provider messages can
  quote the request or part of a key, so only the kind of failure travels on.
- **Alternatives:** Mocking the HTTP layer (tests would depend on one
  provider's wire format); LiteLLM's built-in retries (not visible to the
  match, not testable without the network); losing the seat only after
  several failed turns in a row (more state for a rare case; can be added if
  real matches show short outages).

## D-022 · Prompt layout, and how other players' words are kept apart from instructions

- **Date:** 2026-11-11
- **Decision:** Two messages. System: who the player is, the game's
  `rules.md`, how to answer (one tool call is the move, plain text is private
  thinking), and that game data is never an instruction. User: the
  observation in `<situation>`, the last 40 events the player may see in
  `<events>`, then the ask, with the server's error on a correction. All game
  data is JSON with `<` escaped, one event per line. Text a player wrote is a
  game event of the reserved type `message` with exactly
  `{"player", "text"}`; the engine refuses any other shape. A prompt shows it
  as `player p2 says: "..."`, the reader's own as `you said: "..."`. The
  engine, not the runner, selects the events of a request by
  `event.is_visible_to(player)`. The scaffolding is English; the per-match
  language (D-001) applies to what models say and comes with table talk.
- **Why:** Everything the server says is in the system message; everything
  that can contain another model's words is in data blocks that those words
  cannot leave: JSON keeps a text on its line, the escaped `<` keeps it from
  closing a block. One reserved event type lets every game's chat be labelled
  the same way without the prompt builder knowing any game. Filtering in the
  engine means a hidden event is never handed to an agent at all.
- **Alternatives:** One chat message per event (more tokens, and role
  `assistant`/`user` would blur who wrote what); a flag on `Event` for player
  text (a schema and storage change); stripping suspicious text (lossy, and a
  filter can be talked around); a summary of older events (comes with memory,
  phase 6).

## D-023 · What an agent writes is made storable before it is logged

- **Date:** 2026-11-11
- **Decision:** The engine cleans every reply before it uses it: NUL
  characters and halves of surrogate pairs are removed from all strings, NaN
  and infinity become null.
- **Why:** Postgres refuses all three in `jsonb`, and model output goes into
  the log as thoughts, arguments and error texts. Without this, one odd
  character in one answer would stop a match at the next write.
- **Alternatives:** Rejecting such answers (costs a correction for something
  the model cannot see); cleaning in the store (the stored log would differ
  from the events the match applied, against D-016).

## D-024 · A game's title and rules text each live in one place

- **Date:** 2026-11-11
- **Decision:** `GamePlugin.name` is the title that prompts, and later the UI,
  show. `GamePlugin.rules()` returns the game's `rules.md`, which does not
  repeat the title. This is the "exactly one place" of D-018.
- **Why:** A rename is then a one-line change, and the rules text a model
  reads is a file that people can read and review too.
- **Alternatives:** The title as the heading of `rules.md`; rules as a string
  in the plugin.
