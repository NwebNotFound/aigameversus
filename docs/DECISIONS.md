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

## D-019 · Throne of Tokens data: layout and loader

- **Date:** 2026-11-11
- **Decision:** Content lives in `games/civ/data/` (events in
  `games/civ/data/events/`, not `games/civ/events/` as one spec line says, to
  match the repo layout in the same spec). Lists are YAML lists of entries with
  an `id`, so duplicates are caught (YAML mappings silently drop duplicate
  keys). One event per file, file name = id. Pydantic models in
  `games/civ/data_loader.py` are the single source of the schema; the
  `*.schema.json` files are generated from them and a test fails when they are
  stale. Building-slot numbers sit in `balance.yaml` only, not also in
  `buildings.yaml`.
- **Why:** One place for each number; readable errors; editor validation for
  free.
- **Alternatives:** hand-written JSON schemas validated with `jsonschema`;
  one file per unit and building; id-keyed mappings.

## D-020 · Throne of Tokens values the spec leaves open

- **Date:** 2026-11-11
- **Decision:** Starting values, all in the data files and meant to be tuned:
  - Event chance per round: plague 4 %, drought 3 % (food −50 %, radius 2,
    3 rounds), rebellion 5 % (only cities conquered within 10 rounds), barbarians
    5 % (2 spearmen, 1 swordsman), gold find 5 % (+25 gold), good harvest 6 %
    (+5 food).
  - Treaties: peace and alliance last until broken; non-aggression and open
    borders 3–30 rounds (default 10); tribute 1–20 (default 5). An alliance
    includes open borders.
  - Reputation starts at 50. Trade fee 10 %, +10 % below reputation 30.
  - Start stock 5 food, 5 wood, 0 iron, 5 gold, besides the capital and units.
  - City focus: growth → food, production → wood, military → iron.
  - Pillage yields 50 % of the building's cost. One of each building per city.
  - Divisions in the score and in building slots round down.
  - English ids: Reiter = `horseman`, Belagerung = `siege_engine`,
    Schmiede = `forge`, Speicher = `granary`.
- **Why:** The spec gives no number for these; these keep events rare enough
  not to decide a 60-round match on their own.
- **Alternatives:** leave them out until the systems need them (phase 7
  engine work would then block on data).

## D-021 · Liar's Deck devil card is one of the jokers

- **Date:** 2026-11-11
- **Decision:** In the devil-card variant the devil card is one of the two jokers
  (`devil_card: {card: joker, count: 1, trigger: revealed_on_liar_call, effect:
  all_others_shoot}` in `games/liars_deck/variants/devil_card.yaml`). The deck
  stays at 20 cards. When a "Liar!" call reveals it, every living player
  except the one who played it (the caller included) shoots at the same time,
  and the normal shot of that round is skipped (`replaces_normal_shot: true`).
- **Why:** The spec says "one card is the devil card" without saying which. A
  joker keeps the deck size and the table-card rules unchanged.
- **Alternatives:** A 21st card; one king, queen or ace marked as devil.

## D-022 · Werewolf role selection: wolf count and balance light

- **Date:** 2026-11-11
- **Decision:** For the selection rules ("at least 1 wolf", "wolves fewer
  than half the players") the White Werewolf (team `solo`) counts as a wolf,
  like the roles of team `wolves`, because it hunts with them. The balance light sums `weight × count`
  over the filled selection: above +5 is *village*, below −5 is *wolves*,
  anything from −5 to +5 is *even*, i.e. less than one werewolf's weight (−6)
  away from 0. "Zufällig ausgewogen" draws 300 random playable mixes from the
  match seed (wolf count, special roles on both sides, villagers for the rest)
  and keeps the first one closest to the template's `target_balance`. Problems
  carry a stable `code` and the role id, so the UI can translate the English
  message.
- **Why:** A fixed margin tied to the strongest repeatable role is easy to
  explain next to the light; counting the White Werewolf keeps 3 wolves plus it
  from passing as "3 wolves".
- **Alternatives:** a margin scaled by player count; counting only team
  `wolves`; picking the random mix by search instead of sampling.

## D-023 · Werewolf "Klassisch" scales its wolves with the table

- **Date:** 2026-11-11
- **Decision:** The Klassisch template has `by_players`, a per-size table in
  `games/werewolf/templates.yaml` that overrides the werewolf count: 2 wolves
  for 6-8 players, 3 for 9-15, 4 for 16. Seer, witch and hunter stay one each;
  villagers fill the rest. `apply_template` reads the table; there is no wolf
  formula in code.
- **Why:** The balance light (D-022) must not favour the village. With the
  fixed roles the total is `11 + players - 7 * wolves`: +3, +4, +5 for 6-8
  players, -1, 0, +1 for 9-11, +2 to +5 for 12-15 and -1 for 16. The light is
  *even* at every size from 6 to 16. 6-8 players cannot get closer to 0 (3 of
  6 is not allowed, 3 of 7-8 is a large share of a small table). Wolves stay
  under half the players everywhere. A test checks every size.
- **Alternatives:** `max(2, players // 4)` wolves, i.e. 2 wolves up to 11
  players (rejected: leaves 9-11 players village-favoured at +6 to +8); a
  formula field in the template format.

## D-024 · An agent answers with one action and a thought; thoughts are an engine channel

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

## D-025 · The turn clock is in the engine, and an agent that gives up loses its seat

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

## D-026 · One model-call boundary; the runner retries; the mock LLM stands behind it

- **Date:** 2026-11-11
- **Decision:** The agent runner (`ModelAgent`) reaches its model only through
  a `ModelCall`: messages and tool schemas in, text and raw tool calls out,
  `ModelError(reason, retryable)` on failure. `MockLLM` and `LiteLLMModel`
  implement it. The runner retries a failed call 3 times with pauses of 1, 2
  and 4 seconds; a failure marked as not retryable (wrong key, bad request) is
  not retried. When that is used up, the model counts as failed for good: the
  runner raises `AgentError` and the engine takes the seat (D-025). LiteLLM's
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

## D-027 · Prompt layout, and how other players' words are kept apart from instructions

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

## D-028 · What an agent writes is made storable before it is logged

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

## D-029 · A game's title and rules text each live in one place

- **Date:** 2026-11-11
- **Decision:** `GamePlugin.name` is the title that prompts, and later the UI,
  show; code never writes a title anywhere else. This is the "exactly one
  place" of D-018. `GamePlugin.rules()` returns the game's `rules.md`. The
  prompt puts the `name` above the rules, so a rules text does not need the
  title. The rules texts written before their plugins (Liar's Deck, Poker,
  Werewolf, Throne of Tokens) still open with a title heading; it goes when
  each game gets its plugin.
- **Why:** A rename is then a one-line change, and the rules text a model
  reads is a file that people can read and review too.
- **Alternatives:** The title as the heading of `rules.md`; rules as a string
  in the plugin.

## D-030 · Spectator UI: SvelteKit 3 on Node, API calls server-side, English chrome

- **Date:** 2026-11-11
- **Decision:** `web/` is a SvelteKit 3 app in TypeScript with
  `@sveltejs/adapter-node`, run as `node build` in a `node:24-alpine` image on
  container port 3000 (host 3100). Pages load API data in server `load`
  functions through `web/src/lib/api.ts`; the base URL is the env var
  `ARENA_API_URL` (`src/env.ts`, default `http://127.0.0.1:8100`; in Compose
  `http://arena:8000`). Until `GET /matches` exists the arena answers 404, which
  the client treats as "no matches running"; no answer or a 5xx shows "Arena
  unreachable". Lint is Prettier plus `svelte-check` (no ESLint); unit tests
  use Vitest, smoke tests Playwright at 375 and 1280 px. The UI text is English;
  the in-game language stays a per-match setting (D-001). Supersedes D-005.
- **Why:** Server-side calls need no CORS on the API and keep the API address
  out of the browser. A Node server is also where the live WebSocket relay can
  sit later. English matches the public repo; match content is translated per
  match anyway.
- **Alternatives:** `adapter-static` with browser calls and CORS; ESLint;
  German UI text.

## D-031 · Multiplayer Elo, the overall rating, and rating storage

- **Date:** 2026-11-11
- **Decision:** A match counts as every pairwise duel between its players
  (ahead = win, same rank = draw) with the classic expectation
  `1 / (1 + 10^((opponent − own) / 400))`. A player's change is
  `K / (n − 1) × Σ (score − expected)`, with K = 32 by default, so the winner of
  a 6-player match among equals gains as much as the winner of a duel (+16).
  Deltas of a match sum to zero. Ratings are floats, rounded only for display.
  Everyone starts at 1000 per game. The overall rating is the mean of a
  player's per-game ratings weighted by games played (1000 with no games).
  Storage: `player_profiles`, `ratings` (one row per profile and game) and
  `rated_matches`. Applying a match first claims its id in `rated_matches`, so
  the same match never counts twice, and does everything in one transaction
  with rows locked in profile-id order. The migration is forward-only like all
  others (D-014), so there is no down step.
- **Why:** Normalising by opponents keeps ratings comparable across games with
  2 to 16 players. Weighting by games played stops one lucky game in a rarely
  played title from moving the overall rating as much as fifty poker matches.
- **Alternatives:** unnormalised pairwise K (big tables swing ratings n − 1
  times as hard); TrueSkill or Glicko (better uncertainty, harder to explain);
  a plain mean or the maximum of per-game ratings for the overall value.

## D-032 · Leaderboard: per-match placements, demo seed, display rules

- **Date:** 2026-11-11
- **Decision:** A new table `match_placements` (migration 0003) keeps each rated
  player's rank, table size and rating before and after, per match. Win rate
  (share of matches at rank 1), average placement and a profile's recent
  matches come from it. `GET /leaderboard?game=<id>` returns rows sorted by
  rating, then name; without `game` it uses the overall rating (D-031) and sums
  games, wins and placements over all games. The row `rank` is the position on
  the board. Ratings and changes are rounded to one decimal in API answers and
  to whole numbers in the UI. Profiles without a rated match are left off the
  board. Relations and memory on a profile are explicit "not available yet"
  placeholders until phase 6. `python -m arena.ratings.demo_seed` fills the
  tables with six "DEMO …" profiles (model `random-bot`, fixed ids) playing
  real High Card matches as random bots, with match ids derived from the seed:
  re-running adds nothing, and it refuses when any non-demo profile exists.
  CI seeds its fresh database for the leaderboard Playwright tests.
- **Why:** Win rate and placement cannot be derived from the rating rows alone,
  and storing them per match also gives match history. Demo data from real
  bot matches exercises the same write path as real results, at no cost.
- **Alternatives:** counters on `ratings` (no history); computing stats from
  the event logs on each request; a static JSON fixture for the UI.

## D-033 · Liar's Deck engine: turns, talk, thoughts and open rules

- **Date:** 2026-11-11
- **Decision:**
  - Card ids name the rank (`K1`-`K6`, `Q1`-`Q6`, `A1`-`A6`, `J1`, `J2`); in
    the devil-card variant the devil joker is `DV` and its holder sees it.
    Other players never see ids of unrevealed cards.
  - Each revolver is loaded once per match (live chamber by seed, spectators
    only) and is not reset between rounds, so the risk keeps rising.
  - The first round starts with the first seat. After a call, the next round
    starts with the player who pulled the trigger if alive, otherwise with the
    other side of that call; after a devil card, with its player.
  - `table_talk` does not end the turn and is allowed once per turn; every
    text (talk, claim, call) has at most 40 words. Words go out only as
    `message` events.
  - There is no `think` tool: private thoughts are the plain text of a
    model's answer, which the engine's thoughts channel already logs for
    spectators only. `rules.md` says so.
  - "Only one player holds cards" makes that player call automatically. A
    play that leaves no other holder is checked by the next living player;
    normal play cannot reach this, it is a safeguard.
  - `render_spec(state)` exists on the plugin as a plain method (a card-table
    layout with every hand, never the live chambers) and is not added to the
    `GamePlugin` interface until the UI defines it (see D-009).
- **Why:** The spec leaves these open; each choice keeps one action per turn,
  keeps hidden information out of other players' views and reuses the
  engine's existing channels instead of adding parallel ones.
- **Alternatives:** talk as part of every action only; a `think` tool that
  emits a spectator-only event; reloading revolvers each round; a random
  first starter.

## D-034 · Money is counted per model call, in a ledger, before the call is sent

- **Date:** 2026-11-11
- **Decision:** Every model call of a match goes through `Budget.meter`
  (`arena/agents/budget.py`). Before the call is sent it is booked in the
  `model_calls` table at the most it can cost: the size of the request in
  bytes as its input tokens, the output limit as its output tokens. If that
  booking would take the match or the calendar month (UTC) past its cap, the
  call is not sent. When the provider reports the tokens, the booking is
  corrected to the real cost. A call that reports nothing (an error, a
  timeout, an answer without usage, a crash) keeps its upper bound. Should a
  provider report more than the bound, the real cost is booked all the same:
  the cap is then passed by that difference, and the next call pauses. Check and
  booking are one transaction under an advisory lock. Money is an integer of
  millionths of a euro, rounded up per call. A prompt whose upper bound is
  above `max_input_tokens` is not sent; that seat goes to the random bot.
  `Budget.model` is the only place that builds a real model, already metered.
- **Why:** "Hard cap" has to hold in the cases where counting afterwards
  fails: several players calling at once, a turn that times out while the
  provider still answers and bills, a process that dies between call and
  bookkeeping, two processes running matches. Booking the worst case first
  covers all of them with one rule, and every error is on the safe side: the
  ledger can show more than was billed, never less. No tokenizer produces
  more tokens than its text has bytes, so the bound needs no tokenizer and
  holds for every model, as long as the provider keeps to the output limit it
  was sent. If one does not, a ledger that tells the truth is worth more than
  a cap that looks kept. Integers keep sums exact and identical in any order.
  The input limit also keeps prompts below the sizes at which some providers
  charge a higher price per token.
- **Alternatives:** Adding up the cost after each call (a cap can be passed
  by as many calls as are in flight, and a cancelled call is never counted);
  charging nothing for failed calls (wrong when the provider billed a call
  that timed out on our side); LiteLLM's built-in cost tracking (prices come
  from a list bundled with the library, in memory only); the cost a provider
  reports per call (provider-specific; can replace the price list later);
  cost events in the match log (a dropped turn would lose them, D-035).

## D-035 · At a cap the match pauses: the turn is dropped and played again later

- **Date:** 2026-11-11
- **Decision:** An agent that cannot go on without the user raises
  `MatchPaused(reason, **data)`; the budget does so with `match_cap` or
  `month_cap` and the amounts. The engine cancels the other players of that
  turn, drops everything the turn produced, logs `match_paused` (spectators
  only), hands the log to the sink and lets `Match.run()` raise the pause.
  Whoever started the match asks the user. `run()` again logs `match_resumed`
  and plays the dropped turn from its start. The budget's caps are plain
  attributes that the caller raises after the user agreed.
- **Why:** A match that stops costing money must also stop its turn clock,
  otherwise waiting for the user would turn into random moves. Dropping the
  whole turn keeps the rule that a stored log never ends inside a turn, so a
  paused log replays like any other, and the game goes on exactly as if there
  had been no pause. An exception cannot be overlooked by a caller the way a
  special return value can. The price is that a turn interrupted by a pause
  asks its players again; that happens once per pause.
- **Alternatives:** Letting the random bot play at the cap (silently changes
  who plays); ending the match; keeping the answers already given in the
  paused turn (a second kind of half-finished turn in the log and in replay);
  waiting inside the model call until the user decides (the engine would not
  know that the match is paused).

## D-036 · `config/models.yaml`: limits and prices next to the roster

- **Date:** 2026-11-11
- **Decision:** `config/models.yaml` has two parts. `limits`: the caps in
  euros (0.50 per match, 5.00 per month, D-001), the dollar-to-euro rate, and
  the token limits of one call (50 000 in, 1 500 out). `models`: id,
  `provider`, the provider's model name and the two prices in US dollars per
  million tokens. The default roster is eight cheap OpenRouter models from
  eight vendors that support tool calls, with the prices openrouter.ai listed
  on 2026-11-11. The rate is 1.0: a dollar counts as a full euro. `provider`
  accepts only `openrouter` for now. `arena/config.py` validates the file;
  unknown fields are errors. `tier` and `base_url` from the spec are left out
  until something reads them (tool sets per model size, local models).
- **Why:** The caps are only as good as the prices, so prices sit in a file
  that people review, next to the model they belong to, in the unit the
  provider publishes. A rate of 1.0 errs on the safe side while a dollar is
  worth less than a euro and needs no exchange-rate service. Refusing unknown
  fields catches typos and a key pasted into the wrong file.
- **Alternatives:** Prices from LiteLLM's bundled list or from the provider's
  API at startup (network at startup, and a silent change of what a cap
  means); caps in environment variables; prices already converted to euros.

## D-037 · LiteLLM's own logger is switched off

- **Date:** 2026-11-11
- **Decision:** `LiteLLMModel` disables the `LiteLLM` logger when it loads the
  library. The arena logs only the kind of a failure (D-026).
- **Why:** At debug level LiteLLM logs every request and every provider error
  text. Such a text can quote a key, and a request holds a player's private
  view of the game. A test runs a match at debug level with a provider error
  that quotes the key and finds neither in logs, output, events or the ledger.
- **Alternatives:** A filter that redacts known secrets from all log records
  (cannot know every secret, and prompts would still be logged); raising the
  logger's level only (any later `setLevel` brings the text back).

## D-038 · Poker betting: minimum raise, short all-ins, side pots, odd chips

- **Date:** 2026-11-11
- **Decision:** `games/poker/betting.py` implements No-Limit betting rules as
  pure code. `raise(amount)` names the total bet for the round ("raise to").
  The minimum raise is the current bet plus the size of the last full raise,
  and at least the big blind; before the flop that is double the big blind, as
  the spec's "double the last bet". An all-in below a full raise does not
  reopen raising for players who already acted: they may only call or fold,
  and going all-in is refused for them when it would put in more than a call.
  A big blind posted short does not lower the bet: the others still owe the
  full big blind (the short blind is all-in, side pots sort out the rest).
  Side pots come from each player's total contribution in the hand; folded
  chips stay in the pots, and a pot that only one player can win returns an
  uncalled bet. Odd chips of a split pot go one each to the winners in seat
  order starting left of the button.
- **Why:** These are the standard tournament rules; they keep every chip
  accounted for and are what poker players and models expect.
- **Alternatives:** the spec's literal "double the last bet" for every raise;
  odd chips to the best hand by suit; letting short all-ins reopen raising.

## D-039 · Poker tournament: button, dealing, duplicate mode, statistics

- **Date:** 2026-11-11
- **Decision:**
  - Tournament defaults are settings: `starting_stack` 1000, `small_blind` 10
    (big blind double), `double_every` 10 hands, `hand_limit` 100. At the limit
    the bigger stack ranks higher; equal stacks share a rank.
  - The button moves to the next seat that still has chips (a simple moving
    button, no dead button). With two players the button posts the small blind
    and acts first before the flop, last after it. A blind a player cannot
    afford is posted all-in. No antes, no burn cards.
  - The deck is shuffled once per hand and logged for spectators only. Hole
    cards go out by seat position, two per seat, in seat order; the board takes
    the next cards. Duplicate mode (`duplicate: {deck_seed, rotation}`) shuffles
    from `deck_seed` instead of the match seed and rotates the seating by
    `rotation`, so a rematch with the next rotation deals the same cards to the
    same seats with different players in them (DESIGN.md "Fairness"). Pairing
    the rematches is the game master's job.
  - Players knocked out in the same hand rank by chips at the start of that
    hand; equal chips share a rank.
  - Opponent statistics in the observation: hands dealt, hands played
    voluntarily (a call or raise before the flop), raises, showdowns, and
    shown bluffs (made the last bet or raise of a hand that went to showdown
    and won nothing).
  - Like Liar's Deck: `table_talk` once per turn without ending it, at most
    40 words, words only as `message` events; no `think` tool, thoughts are
    the plain text of an answer. `render_spec` is a plain method, not part of
    the interface yet.
- **Why:** Standard tournament practice where the spec is silent; seat-based
  dealing is what makes duplicate rematches fair.
- **Alternatives:** dead-button rules; a random first button; dealing from the
  small blind; a fixed duplicate pairing inside one match.

## D-040 · A match has a turn limit

- **Date:** 2026-11-11
- **Decision:** `GamePlugin.max_turns` is the most turns a match of the game
  can take; the default is 10 000 and a game sets its own (High Card: one
  turn per card, 20). `Match(max_turns=...)` overrides it for one match. When
  a match is still not over after that many completed turns, the engine logs
  `turn_limit_reached` (spectators only), hands the log to the sink and raises
  `PluginError`. A turn dropped by a pause does not count.
- **Why:** The engine already stops a turn without progress, but a plugin bug
  can also make progress forever: rounds that never end the game. Such a
  match would fill the event store and, with models, spend up to the cost
  cap. A limit on the plugin sits next to the rules that justify it.
- **Alternatives:** A time limit for the whole match (depends on how fast the
  models answer, and a pause would need an exception); a limit on events
  (harder to derive from the rules of a game); only a per-match setting (every
  caller would have to know every game).

## D-041 · A game is found by its folder

- **Date:** 2026-11-11
- **Decision:** `arena/games.py` lists the games: every package `games/<id>/`
  with a `plugin.py` that defines exactly one `GamePlugin` class whose `id` is
  the folder name. The class is created without arguments. A package without
  `plugin.py` is skipped (data of a game that is not written yet); a
  `plugin.py` that breaks the rule stops the start with an error that names
  it.
- **Why:** The spec promises that a new game is a new folder and nothing
  else. One rule, checked at start, also keeps a game id, its folder and its
  stored logs under one name.
- **Alternatives:** A list of games in code or config (a second place to
  edit); entry points (packaging for something that lives in this repo);
  skipping broken folders (a game silently missing from the list).

## D-042 · Matches from the API run inside the API process; spectators read the log over WebSocket

- **Date:** 2026-11-11
- **Decision:** `POST /matches` starts a match as an asyncio task of the API
  process. Its events are stored turn by turn; `WS /matches/{id}/events`
  sends the log from its first event, waits for new turns while the match
  runs, and closes when it stops. A match that is over is sent from the event
  store. Only completed turns are shown. A `matches` row holds what was asked
  for and how it ended: `running`, `finished`, `failed`, `interrupted`. When
  the server stops, its matches stop; the next start marks them
  `interrupted`. `turn_delay` (0 to 60 s) paces a match for watching. Seats
  are random bots only until model seats come with phase 2. The server plays
  at most 10 matches at a time and answers 429 to a start beyond that; with
  the turn limit (D-040) this bounds what requests can make it store. The server speaks
  WebSocket through the `websockets` package, a dependency of its own because
  plain `uvicorn` brings none.
- **Why:** One process needs no queue and no message bus to get a live
  stream, and a bot match lasts milliseconds. Sending the log from the start
  gives a late spectator, a reconnect and a replay the same simple protocol,
  and the stream can never show something that is not stored. A match cannot
  be continued in another process yet, so saying `interrupted` is the honest
  status.
- **Alternatives:** Running matches in the worker with Redis for the stream
  (the Compose services exist for it; worth it once matches are long or
  many); server-sent events (the UI will also send controls); streaming only
  new events and loading the past over HTTP (two code paths in every client);
  continuing interrupted matches from the log (needs agents that can be
  rebuilt; later).

## D-043 · The `arena` command plays in its own process

- **Date:** 2026-11-11
- **Decision:** `arena run --game <id> --bots` runs the engine in the command's
  own process and prints every event with its position and audience. It uses
  no server and no database and stores nothing. `--bots` is required: it is
  the only kind of player the command offers so far. A seed is chosen and
  printed when none is given.
- **Why:** The first thing anyone tries should work with `uv run` alone and
  cost nothing. Printing the seed makes every run repeatable.
- **Alternatives:** A command that calls the API (needs the stack; the API
  can be called with curl); storing command-line matches when a database is
  configured (behaviour that depends on the environment).

## D-044 · A game reads nothing from the order of keys in event data

- **Date:** 2026-11-11
- **Decision:** Event data is JSON whose objects have no order: plugins use a
  list wherever order matters. `tests/test_games.py` plays a bot match of
  every game and replays its log with the keys of every object reversed.
- **Why:** Postgres `jsonb` does not keep key order, and the engine's check
  that event data survives JSON (D-016) compares with `==`, which ignores
  order. A plugin that iterated over such an object would replay differently
  from how it played.
- **Alternatives:** Storing events as `json` instead of `jsonb` (keeps the
  order in Postgres only, not in other stores or exports).

## D-045 · Turn limits of Poker and Liar's Deck are upper bounds from the rules

- **Date:** 2026-11-11
- **Decision:** Each game's `max_turns` (D-040) is what its rules allow at most,
  computed, not guessed. **Liar's Deck:** every round ends with at least one
  trigger pull and a revolver has 6 chambers, so at most players × chambers
  rounds; a round has at most one play per dealt card plus the call; every
  action may carry one `table_talk` turn: 4 × 6 × 21 × 2 = 1,008.
  **Poker:** `turn_bound()` sums over the hands: 4 streets × players, plus at
  most (players − 1) more actions per raise; a full raise lifts the bet by at
  least the big blind, so a hand holds at most all chips ÷ big blind full raises
  plus one short all-in per player; each action may carry one `table_talk`
  turn. With the defaults and 6 players that is 70,400. Settings whose bound is
  higher (bigger stacks, more hands, smaller blinds) are refused.
- **Why:** A bound from the rules can never stop a legal match, and still stops
  a looping one.
- **Alternatives:** a measured maximum with a safety factor; one large limit for
  every game; letting the bound grow with the settings by overriding
  `Match(max_turns=...)` per match.

## D-046 · Werewolf engine: step queue, night order, deaths and wins

- **Date:** 2026-11-11
- **Decision:**
  - The match is a queue of single-player steps (sequential turn mode): night
    actions sorted by the role files' `night_order` (seat order within one
    slot), one wolf step per pack member at slot 6, the day's speeches (two
    rounds, starting at a seeded position among the living) and one vote per
    living player in seat order, and death effects. `night_started`,
    `day_started` and `player_died` rebuild the queue in `apply_event`, and
    `step_done` (spectators only) ends a turn.
  - Abilities live in `games/werewolf/abilities.py`, keyed by the handler
    names in the role files. A role whose handlers are not implemented cannot
    be put in a match; the random template draws only from playable roles.
  - Wolves may chat twice per night (40 words each) before their vote; the
    victim is the most-voted target, on a tie the first of the tied targets
    voted for. The Witch sees the victim only on her turn and may heal and
    poison in the same night.
  - Day vote: the most votes are executed; abstentions do not count; a tie
    (or no votes) executes nobody. A vote reason is a public message.
  - A dead player's role is revealed to everyone.
  - The winner is checked after the morning and after the execution and their
    death effects: village when no pack member lives, wolves when the living
    pack is at least as big as everyone else, nobody when all are dead. The
    winning side shares rank 1, the rest the next rank.
  - A match still undecided after the 30th day ends without a winner
    (`game_over` with `reason: night_limit`). With that, `max_turns` (D-040)
    is a true bound: 30 × `cycle_turns(16)` = 9,660, where one night and day
    holds at most one role step, one wolf step and two wolf chats per player,
    the Prime Wolf's choice, one captain vote, two speeches, one vote and two
    death effects per player, each of them possibly with a lover chat.
  - Targets are JSON-schema enums of the legal players, so the engine rejects
    illegal targets and the random bot picks from them. No `think` tool, as
    in D-033; `render_spec` is a plain method.
- **Why:** One queue makes every phase, the night order and the death
  chains of later roles the same mechanism, and keeps replays exact.
- **Alternatives:** simultaneous night actions; a strict-majority day vote;
  hidden roles after death; a random tie-break for the pack.

## D-047 · Werewolf day: captain, narrator and language

- **Date:** 2026-11-11
- **Decision:**
  - The captain is elected at the start of day 1, before the discussion,
    when `captain` is on (default from `options.yaml`). Every living player
    votes once in seat order; most votes win, a tie is broken by the match
    seed. The captain's day vote counts `vote_weight` (2). A dying captain
    names a living successor right away (after the Hunter's shot if the
    captain is the Hunter). There is no new election later.
  - The narrator is template text in the match `language` (`de` default per
    D-001, or `en`): a public `narration` event with `key`, the facts and the
    `text`, at nightfall, each morning, the captain's election and handover,
    each vote result and the end. `arena/gamemaster/narrator.py` can retell a
    narration with any `ModelCall` (style plain, epic, news or sports, at most
    60 words); on a model error, an empty or an overlong answer the template
    text stands. Facts go into the prompt as escaped JSON data. Nothing calls
    it yet; the match runner (step 1.6) decides where narration is retold.
- **Why:** The plugin never calls a model (rule 6), but the log always has a
  readable narrator line, and a model can only add colour, never change facts.
- **Alternatives:** captain elected after the first discussion; a new
  election when the captain dies without successor; the narrator inside the
  plugin with a model call.

## D-048 · Throne of Tokens map: rows of hexes, start regions from data, land in one piece

- **Date:** 2026-11-11
- **Decision:** The map is a rectangle of hex tiles, ten per row, with six,
  seven or eight rows for four, five or six nations (60 to 80 tiles, mountains
  and water included). A tile is `(col, row)` and odd rows sit half a tile to
  the right. The map is stored as rows of terrain ids plus one start per
  nation. The spec asks for fair starts and for every nation to be short of
  one resource; the generator does it like this:
  - Capitals are picked greedily, each as far as possible from those before
    it, and the most widely spread of 20 such picks is used. Start regions
    (the six tiles a capital works) never share a tile and are never cut off
    by the rim. Which seat gets which capital is shuffled.
  - The tiles around a capital come from `map.start_regions` in
    `balance.yaml`: one list per scarce resource, all with the same total
    yield (12), laid out in random order. The four shortages are dealt out in
    turn, so with four nations each is short of something different.
  - Every other tile is drawn from `map.terrain_weights`. A draw whose land is
    not one piece is thrown away and drawn again.
  - The two iron deposits and two gold veins go outside the start regions,
    where the nearest capital has the smallest lead over the second nearest
    and that one is close, and never side by side.
- **Why:** A rectangle in rows is what a browser draws and a model reads most
  easily, and rows of ids pass through JSON without depending on key order
  (D-044). Equal start regions make fairness something a test can check, not
  a matter of luck with the seed. Land in one piece means no nation is locked
  in and no tile is unreachable. Rare tiles between nations give them
  something to fight or trade over, which is what the spec wants iron for.
- **Alternatives:** A hexagon-shaped map (its sizes jump from 61 to 91
  tiles); mirrored maps (fair, but every match looks alike and the shortages
  could not differ); judging random starts by a score and redrawing (fairness
  only on average); rivers along tile edges (the spec lists river as a
  terrain with its own yield).

## D-049 · Fog of war: a nation sees what is in range now, by distance alone

- **Date:** 2026-11-11
- **Decision:** A nation sees the tiles within the radius of each of its
  viewpoints (cities and armies; 2 by default, more with a watchtower or a
  scout). Sight is plain distance: mountains and forests do not block it.
  `map_view` gives the terrain of those tiles and `None` for all others. No
  memory of tiles seen earlier is kept.
- **Why:** This is the rule as the spec states it, and it is the smallest
  one: the view is a function of the current state, so nothing about it has
  to be stored or replayed. The systems that own cities and armies pass their
  viewpoints with the radius each has.
- **Alternatives:** Remembering explored terrain (needs state per nation;
  can be added in the turn flow, step 7.6, if matches show that models lose
  their way); line of sight (more rules for models to hold in mind, little
  gain on a map this small).

## D-050 · Werewolf roles batch A: lovers, Protector, Little Girl, Elder, Idiot, Scapegoat

- **Date:** 2026-11-11
- **Decision:**
  - Cupid links two different living players on night 1 (himself allowed).
    Only Cupid sees the link event; the lovers learn each other. A lover's
    death kills the other at once ("grief"), through every death path.
    Lovers may `lover_chat` (40 words, lovers only) once in any of their
    turns without ending it. Lovers from both sides (one in the pack, one
    not) win alone when they are the last two alive, and count for neither
    side's win.
  - The Protector protects one living player a night (himself allowed), never
    the same one twice in a row. Protection stops the wolves' kill, not the
    Witch's poison.
  - The Little Girl may `spy` or `stay_in_bed`. Spying rolls twice from the
    match seed: 30 % she learns one random living wolf (private), 15 % she is
    caught (spectators only) and then becomes the wolves' victim in place of
    theirs. The Protector and the Witch can still save her.
  - The Elder survives the first wolf attack (he alone learns it). If the
    village executes him, every village-team role loses its powers for the
    rest of the match: their night steps and passive hooks stop, except a
    lover's grief.
  - An executed Village Idiot survives, is revealed, and no longer votes.
  - On a real tie (two or more top targets with votes) a living Scapegoat
    dies instead of nobody; no votes at all is not a tie.
- **Why:** The spec's role texts leave these open; each rule keeps one clear
  answer per case and fits the existing step queue and death chain.
- **Alternatives:** lovers win with their teams; protection against poison;
  wolves informed when they catch the girl; the Elder surviving poison.

## D-051 · Werewolf roles batch B: Raven, Wild Child, Prime Wolf, White Werewolf, Bear

- **Date:** 2026-11-11
- **Decision:**
  - The Raven marks a living player (or nobody) at night. If the marked
    player is alive in the morning, the mark is announced publicly (not who
    made it) and adds 2 votes against them in that day's tally.
  - The Wild Child picks a role model on night 1 (not himself). When the
    model dies, by any cause, the child joins the pack: the pack and the child
    learn it, and the child hunts with the wolves from the next night.
  - The Prime Wolf decides after the pack's votes, once per match, whether to
    infect tonight's victim. The choice uses the one infection even if the
    victim is then saved (healed, protected, Elder); a saved victim is not
    infected. An infected player keeps their role and joins the pack.
  - The White Werewolf hunts with the pack, and on even nights may kill one
    other wolf (or nobody). He wins only as the last player alive. The pack's
    win and its winners leave him out; the village needs every pack member,
    him included, dead.
  - The bear growls publicly in the morning if a living pack member is the
    nearest living player on either side of the Bear Tamer in seat order
    (the night's dead are skipped). The growl comes before Hunter and lover
    effects.
- **Why:** The spec's role texts leave these details open; the choices keep
  each effect visible to exactly the players who would know it.
- **Alternatives:** a secret Raven mark; the infection kept for a later night
  when the victim is saved; the White Werewolf counted for the pack's win.

## D-052 · A finished API match rates its random bots

- **Date:** 2026-11-11
- **Decision:** When a match started through `POST /matches` finishes,
  `LiveMatches` (`arena/api/live.py`) applies its placements to the ratings
  (`RatingStore.apply_match_result`, keyed by the match id, so it counts once).
  Every seat has a bot profile, "Random Bot p1", "Random Bot p2", ...
  (`model_id` `random-bot`), created on first use with an id derived from the
  seat name. Failed, interrupted and paused matches are not rated. A rating
  error is logged and never fails the match. `demo_seed` ignores `random-bot`
  profiles when it checks for real profiles. The `arena` command stores
  nothing, so it rates nothing.
- **Why:** A profile can be rated only once per match, so the bots need one
  profile per seat, not one per kind. The leaderboard then fills from real
  matches. Rating after the record is closed keeps the match status true even
  if the rating fails.
- **Alternatives:** one profile per bot kind (impossible: the same profile
  twice in one match); rating only matches with real model players (the
  leaderboard would stay empty until phase 2).

## D-053 · Per-game statistics are pure functions over the event log

- **Date:** 2026-11-11
- **Decision:** Statistics live in `arena/stats/<game>.py` as pure functions
  from the stored event log of one match to a Pydantic model per player
  (`match_stats`), plus `aggregate` over many matches of one player. They read
  only events the plugin already emits. The first one is Liar's Deck: lie rate
  (lies / plays, a lie is a play with a card that is neither the table card nor a
  joker), times caught lying, success rate of "Liar!" calls (only calls the
  player chose to make; automatic calls are forced), rounds survived (rounds
  played minus the round of the fall) and the boldest bluff (the highest
  revolver risk, live chambers left / chambers left, faced while lying).
- **Why:** Computing from the log keeps the numbers reproducible and needs no
  change to a plugin. The helpers in `arena/ratings/stats.py` do the rates, so
  "no data" is `None`, never 0.
- **Alternatives:** counting in the plugin state (changes the plugins, and old
  logs would have no numbers); storing the numbers per match in a table.
## D-054 · Poker statistics: definitions

- **Date:** 2026-11-11
- **Decision:** `arena/stats/poker.py` counts, over the hands a player was
  dealt into: VPIP (a call, raise or all-in before the flop; blinds and a free
  check do not count), aggression factor (aggressive actions / calls; an
  all-in is aggressive only if it goes above the street's highest bet), bluff
  rate (bluff hands / hands with a bet or raise; a bluff hand is a win without
  showdown with less than a pair, or a showdown loss), chips per 100 hands
  (pot shares won minus chips put in, blinds included) and worst decisions
  (a fold whose cards plus the final board would have beaten every shown hand
  at the showdown).
- **Why:** The spec names the numbers but not the formulas. These use only
  events the plugin already emits, including the spectator-only hole cards,
  and chips balance exactly (the net chips of all players sum to 0, which the
  tests check on real bot matches).
- **Alternatives:** counting a showdown loss only when the hand was weak
  (needs a notion of a "strong" hand); counting every all-in as aggressive.
## D-055 · Werewolf statistics: definitions

- **Date:** 2026-11-11
- **Decision:** `arena/stats/werewolf.py` counts per player and match: vote
  accuracy (of the votes for a player cast while on the village side, the
  share that hit a wolf; abstentions are counted separately and wolves' own
  votes are left out), rounds alive (a round is a night and the day after it;
  a player who dies in round `n` was alive for `n` rounds, a survivor for all
  rounds), wins (from `game_over`), and for the seer the rounds she lived and
  whether she died. The wolf side is the pack from `pack_revealed` plus
  `joined_pack` and `infected` players, from the moment they join.
- **Why:** The spec names "vote accuracy, survival, seer outing speed" without
  formulas. Everything comes from events the plugin already emits (the
  spectator log has all roles). "Outing speed" is measured as how long the seer
  lives, since the log has no event for a claim.
- **Alternatives:** counting wolves' votes too (a hit means the opposite for
  them); measuring the outing by chat text (the log has no claim event).

## D-056 · Throne of Tokens economy: one stock per nation, and what the spec leaves open about cities

- **Date:** 2026-11-11
- **Decision:** A nation has one stock of food, wood, iron and gold. Its
  cities fill it and everything is paid from it. Where the spec is silent:
  - **Tiles.** A city works the tiles around it, not the one it stands on;
    the city's own yield (2 food, 1 wood, 1 gold) stands for that tile. A tile
    feeds one city: the nearest that reaches it, the older of two equally
    near. So a city's first ring can only be taken by building on it.
  - **Growth.** The food a city makes beyond what its own population eats
    goes to the stock and also counts towards that city's growth. At 10
    collected the city gains a population and keeps the rest, at most one
    population per round. A city that eats more than it makes takes the
    difference from the stock and collects nothing; nobody starves in a city.
  - **Buildings.** An order is paid at once and takes a slot at once; the
    building works from the next round (`build_rounds` rounds later). Only a
    finished building can be demolished; the refund is rounded down per
    resource. A city that loses population keeps buildings beyond its slots.
  - **Upkeep.** After the yields are in, the population eats, then the units
    take their upkeep. What the stock cannot cover is not paid and the stock
    ends at 0. A round with upkeep not paid in full, in food or gold, is a
    hungry round and costs a random unit; a granary covers the first two
    hungry rounds in a row. Only the nation's best granary counts.
  - **Sight.** A finished watchtower adds its bonus to the sight of its city.
  - Shares of an amount are computed in decimal and rounded down, so 29 % of
    100 is 29 whatever binary fractions make of it.
- **Why:** The spec prices units and trades in food and counts gold per
  nation, so resources cannot belong to cities; but it lets a city grow on
  its own surplus. Counting the surplus twice is the reading that needs no
  rule for sharing food between growth, units and trade, and it is the one
  sentence a model has to remember. Nearest-city tiles need no stored borders
  and never surprise the owner of a ring. Gold upkeep counts like food so
  that a siege engine is not free for a nation without gold. Granaries that
  added up would let a large nation keep an unpaid army for many rounds.
- **Known consequence, for balancing:** on the growth focus a population pays
  for itself, so a capital gains a population almost every round (about 60
  after 60 rounds on the shipped map, against 12 to 18 on the other two
  focuses, where growth levels off). Population counts in the final score.
  `city.growth_food` in `balance.yaml` is the number to raise if bot matches
  show that this decides games.
- **Alternatives:** Growth that uses up the food (units and settlers would
  compete with automatic growth for the same stock, and the player could not
  steer it); a stock per city (needs transport rules); tiles assigned to the
  city founded first (an old city growing to radius 2 would take a
  neighbour's first ring); the city tile also yielding (the map's start
  regions are balanced for six worked tiles); losing population when a city
  cannot be fed (a second starvation rule next to the one for units).

## D-057 · Throne of Tokens state: one model, systems that emit, events that carry outcomes

- **Date:** 2026-11-11
- **Decision:** The game has one state model, `CivState` in
  `games/civ/state.py`, and each system is a module of functions over it
  (`games/civ/economy.py` is the first). A function that changes something
  takes the engine's `TurnContext` and emits events; the module's
  `apply_event` is the only code that writes to the state. An event carries
  what happened in numbers (the cost paid, the refund, the nation's new
  stock), never a reference to a rule, so applying it reads no game data.
  The production of a nation in a round is one event. Every economy event
  is private to its nation. Each order has a `*_problem` function that
  returns a message for the player or `None`.
- **Why:** This is D-009 one level down: the plugin of step 7.6 passes its
  context through and routes events back, and the log rebuilds the state
  with no rules and no data files. Private events keep the fog honest: a
  public "city founded" would give its tile away. One event per nation and
  round keeps a player's recent events, which the prompt shows 40 of, from
  being pushed out by bookkeeping. The check is separate from the order
  because the plugin needs it twice: when a model submits its orders, to
  ask for a correction, and when the round is resolved.
- **Alternatives:** Pure functions that return events for the plugin to
  emit (every step would have to be re-applied by hand before the next one
  can read its result); a state per system (cities are read by fog, combat
  and victory alike); events that name the rule and let `apply_event` look
  the numbers up (an old log would change its meaning when a number is
  tuned); one event per city and round.

## D-058 · Match controls: pause between turns, abort as its own status

- **Date:** 2026-11-11
- **Decision:**
  - Pause, resume, speed and abort act on the match task in the API process
    (`LiveMatches`), not through the database. Only the process that plays a
    match can control it; any other match answers 409.
  - A pause takes effect after the current turn is stored and published, before
    the engine asks for the next turn. No agent, and so no model, is called
    while a match is paused. A pause is not logged as an event: it changes
    nothing in the game, and the same seed gives the same log with or without
    it.
  - A speed change applies at once, also to a wait that has already begun.
  - Abort cancels the task. The record gets the new status `aborted`
    (migration `0006`), with no placements; the stored turns stay readable.
    A match stopped by a server shutdown stays `interrupted`. Once the turn
    with `match_finished` is stored, the match is over: abort answers 409, and
    that last turn does not wait for a resume, so a match paused just before
    its end still ends `finished`. A record that is no longer `running` is
    never closed again.
  - `GET /matches/{id}/board` replays the stored log and returns the game's
    `render_spec`, or `null` for a game without one. `GET /matches/{id}/cost`
    sums the ledger per player.
- **Why:** The live view (roadmap 5.2) needs these controls; doing them in the
  process that owns the task needs no queue or polling. Pausing between turns
  keeps a pause free of cost and the log a clean list of turns.
- **Alternatives:** a `match_paused` event for spectator pauses (they are not
  game events, and a replay should not stop there); aborted matches as
  `failed` (it hides that nobody did anything wrong); a speed change only from
  the next turn (a 30 s wait would ignore the click).

## D-061 · Werewolf "Düsterwald-Mix" scales its wolves; "Chaos" stays as it is

- **Date:** 2026-11-11
- **Decision:** Düsterwald-Mix has a per-size `by_players` table for its werewolf
  count (as Klassisch, D-023): 2 wolves for 8 players, 3 for 9, 4 for 10-16.
  With its six special roles (seer, witch, hunter, Cupid, Bear Tamer, Little
  Girl) the total is `15 + players - 7 * wolves`: +9 at 8 players, then +3, -3,
  -2, -1, 0, +1, +2, +3 for 9 to 16. The light is *even* at 9-16 and within
  -1..1 for 12-14. At 8 players it stays *village* (+9): a third wolf does not
  fit beside six special roles (nine roles for eight seats), so +9 is the
  nearest reachable value. Chaos is unchanged: its 12 non-werewolf roles
  (Prime Wolf and White Wolf among them) and 2 werewolves give `players - 7 *
  wolves`, which is 0, +1 and +2 for its 14, 15 and 16 players. Tests pin the
  totals of both templates at every size.
- **Why:** Fixed 2 wolves left Düsterwald village-favoured everywhere (+9 to
  +17). The table follows the same idea as D-023: wolves grow with the table
  and the light is read from the weights.
- **Alternatives:** dropping a special role from the 8-player mix to allow a
  third wolf (changes the template's roles, not only its counts); a formula
  field in the template format.

## D-062 · The chronicler tells a finished match from templates, behind a Narrator

- **Date:** 2026-11-11
- **Decision:** `arena/chronicle/` builds a chapter-by-chapter story from the
  stored event log of a finished match of Liar's Deck, Poker or Werewolf:
  chapters are rounds, hands and nights, made of beats (a caught lie, a shot,
  an all-in, a death, a vote, the win). `tell(events, style=, lang=, names=)`
  gives a `Chronicle`; `to_markdown` exports it; `GET /matches/{id}/chronicle?
  style=&lang=&format=` serves it. The four styles (epic, news, sports, novel)
  in English and German are fixed templates, so the same log gives the same
  text and nothing is paid. `Narrator` is the interface a model can implement
  later to retell a chapter from its beats; the default `TemplateNarrator`
  needs no model. The story uses spectator information (hidden cards, roles),
  so a log without `match_finished` is refused, and the endpoint answers 409
  for a match that is still running.
- **Why:** A story told during the match would reveal what players may not
  know, and the templates keep tests exact and the cost at zero. Beats keep the
  facts apart from the words, which is what a model narrator needs.
- **Alternatives:** telling the story live from public events only (much
  thinner, and the replay page can use the finished one); one free-text
  generator without beats (not testable).

## D-063 · Profile statistics: seats stored at rating time, totals read from the logs

- **Date:** 2026-11-11
- **Decision:**
  - The rating of a match also stores which seat of its log each profile
    played (`match_seats`, migration `0007`), in the same transaction as the
    ratings. Matches rated without seats (the DEMO seed) have no statistics.
  - `GET /profiles/{id}/stats?game=` loads the log of every rated match of the
    profile in that game, runs the game's `match_stats` from `arena/stats` and
    returns its `aggregate` per game. Nothing is cached: the logs are the truth
    and the statistics follow any fix of a stats module at once. Without
    `game`, every game with statistics the profile played; a game without
    statistics answers 404.
  - At most the newest 200 rated matches per game count (`MAX_STATS_MATCHES`);
    `matches` says how many did.
  - The profile page shows one table per game, the fields of the game's totals
    in their order, shares as percent.
- **Why:** The seat is the only link between a profile and its events; storing
  it when the match is rated keeps one place that knows both. Computing on
  request is fast enough for today's match counts, and the cap bounds a
  random-bot profile, which sits in every bot match.
- **Alternatives:** stored totals per profile and game (to be added when a
  profile has thousands of matches); seats in `match_placements`.

## D-064 · Live view: SSE relay on the web server, a generic board, spoilers in the UI

- **Date:** 2026-11-11
- **Decision:**
  - The browser follows a match through `GET /matches/<id>/stream` on the web
    server, as server-sent events. The web server reads the arena's WebSocket
    and sends each event with its `seq` as the SSE id. Close 1000 becomes an
    `end` event, 4404 `missing`; any other close just ends the response, and
    the browser's EventSource reconnects. The relay skips the positions up to
    `Last-Event-ID`; the page also keeps each position once, so a reconnect
    from the start shows nothing twice.
  - Board, cost and controls come from `GET /matches/<id>/state` (web server),
    reloaded after new events, at most about three times a second. Controls go
    to the same URL as `POST {action}`.
  - Columns: an event with `visible_to = null` is public (middle); every other
    event, thoughts included, is behind the scenes (right). The player filter
    keeps the events whose `player`, `caller` or `target` is that player, or
    that the player may see. Newest events come first.
  - One generic board draws every `render_spec` with `seats` as cards with
    their fields as text; a spec without seats is shown as JSON. The game
    tables of steps 5.4 and 5.5 replace it per `layout`.
  - Spoilers are a UI setting, on by default (spectators see everything,
    DESIGN). Off hides the board fields `hand`, `cards` and `role` and the
    whole right column. The list of secret fields lives in the UI
    (`web/src/lib/live.ts`), not in the plugins.
  - Cost shows four decimals of a euro, rounded up like the ledger.
- **Why:** SSE keeps the rule of D-030 (no browser call to the arena, no CORS)
  and brings reconnects with a resume position for free. Reloading the board
  from the API keeps the board logic in the plugin; the UI never rebuilds
  state. A fixed list of secret fields covers the three games with a board
  today without changing their plugins.
- **Alternatives:** a WebSocket proxy in the Node server (it would need a
  custom server around the adapter's handler); browser calls to the arena with CORS; spoiler marks in each
  `render_spec`; boards built from the events in the browser.

## D-065 · New-match form: bot seats now, models and cost limit shown for later

- **Date:** 2026-11-11
- **Decision:**
  - `/matches/new` is a SvelteKit form action: it works without JavaScript,
    checks every field on the web server (`web/src/lib/new-match.ts`), shows a
    problem next to its field and keeps what was entered, then starts the match
    with `POST /matches` and redirects to its live view. A refusal of the arena
    (422 from the game, 429 when the arena is full) is shown above the form.
  - `GET /setup` (`arena/api/setup.py`) lists the models of
    `config/models.yaml`, the personalities of `config/personalities/`
    (checked against their schema) and the cost caps, with
    `model_seats: false`. As long as it is false, every seat is a random bot:
    the models, the personality per seat and the cost limit (the match cap as
    its default) are shown but disabled, and the web server refuses a model
    seat. Phase 2 enables them; then `POST /matches` needs seats and a limit.
  - Language (de/en, default de) goes into the settings only of games that
    have game text in a language: today Werewolf (its narrator). The other
    games refuse unknown settings.
  - Speed is one of the live view's speeds (default Normal, 1 s per turn).
  - The web container gets `ORIGIN: http://127.0.0.1:3100`. SvelteKit refuses a
    form POST from another origin, and without `ORIGIN` adapter-node expects
    https, which refused every submit of the local stack. `csrf.trustedOrigins`
    in `web/vite.config.ts` also lets `http://localhost:3100` post; any other
    origin is still refused.
- **Why:** The form can be used today for bot matches and already has the
  shape the spec asks for (game, players, models, personalities, cost limit,
  seed), without an API for model seats before the runner can play them.
- **Alternatives:** leaving models and cost limit out until phase 2; accepting
  and ignoring them in `POST /matches`; a language setting for every game.

## D-066 · Werewolf role selection in the new-match form

- **Date:** 2026-11-11
- **Decision:**
  - The form shows the templates for the chosen table size
    (`GET /games/werewolf/templates?players=N`, which gives each template's
    roles at that size, or none when it does not fit). A template that needs
    more players is listed but disabled. Choosing one fills the checklist; a
    template in use follows the player count.
  - Changing a count makes the mix "Custom". The checklist is grouped by team;
    a unique role is a checkbox, any other role a count. Villagers are not
    chosen: they fill the free seats and their number is shown.
  - The web server checks a custom mix a quarter second after each change
    (`/matches/new/werewolf`, which forwards to the arena's selection check)
    and shows its balance light (green when even, amber when it favours one
    side) and its problems: next to the role when the problem names one, above
    the checklist otherwise. On submit the same check runs again before the
    match starts, so a mix that cannot be played is refused at its fields with
    the counts kept.
  - A template goes to the match as `settings.template`, a custom mix as
    `settings.roles` (counts above 0). The random template shows no checklist:
    its roles come from the match seed.
- **Why:** The selection rules and balance stay in `games/werewolf/selection.py`;
  the form only shows what the arena says, so the two cannot disagree.
- **Alternatives:** checking the rules in the browser; a villager count to set
  by hand; a red light for imbalance (the arena has three verdicts, not a scale).

## D-067 · Game tables are components chosen by the render_spec layout

- **Date:** 2026-11-11
- **Decision:** The live view's `Board` picks a table component by the `layout`
  of the plugin's `render_spec` (`card_table` is the Liar's Deck bar table in
  `web/src/lib/components/LiarsDeckTable.svelte`) and falls back to the generic
  board when the spec does not have the fields the table needs. `Board` also
  gets the match log (`events`), so a table can react to what just happened.
  The Liar's Deck table shows a banner for each call ("Liar!") and each shot
  ("click" or "BANG") for 1.3 seconds, in order, at most six at a time, and
  never for the backlog it finds when it appears: replays and reloads do not
  replay the drama. The art is inline SVG and CSS, no files.
- **Why:** The spec is a plain dict, so the UI decides the drawing; falling back
  keeps the live view working for a game without a table. Reading the log
  keeps the plugin free of animation state.
- **Alternatives:** an animation field in `render_spec` (puts UI state in the
  plugin); one component per game chosen by game id (breaks for variants that
  share a layout).

## D-068 · The Poker spectator spec carries side pots and win chances

- **Date:** 2026-11-11
- **Decision:** `Poker.render_spec` adds `side_pots` (the main pot and side pots as
  `{amount, eligible}`, empty when fewer than two players are live) and, per
  seat, `win_probability`: the player's chance to win if the hand ran to the
  river now (`win_probabilities` of `games/poker/evaluator.py`, 400 sampled
  runouts, `None` for folded players). The random stream is fixed by hand number
  and board size, so a state always gives the same numbers. The Poker table
  shows the chances only with spoilers on, and `win_probability` joins the
  fields the UI hides with spoilers off.
- **Why:** The table must show pot and side pots and, optionally, the chances;
  the UI cannot evaluate hands. The chances follow from every hole card, so they
  are spectator information like the hole cards themselves.
- **Alternatives:** a hand evaluator in TypeScript (a second implementation to
  keep in step); a separate API endpoint for the chances (a second request per
  turn); exact enumeration (too slow before the flop).

## D-069 · The Werewolf circle draws votes from the log and shows no model names

- **Date:** 2026-11-11
- **Decision:** The Werewolf circle (`layout: player_circle`) gets its vote arrows
  from the match log, not from the plugin: the votes cast since the day began
  (the last one per voter, an abstention takes a vote back) stay drawn after the
  result until the next night starts, with the count against each player on
  their seat. The backdrop follows the plugin phase: night, dusk or day. Roles
  show only with spoilers on, as a `?` otherwise. Seats show the player id, not
  a model name, because the spectator spec has none.
- **Why:** The votes are public events, so the log is the source and the plugin
  needs no UI state. The spec carries seats and phase only.
- **Alternatives:** adding the votes to `render_spec`; passing the model names to
  the board (needs the match record in the board props, a later step).

## D-070 · Real models take their seats from the command line first

- **Date:** 2026-11-11
- **Decision:** `arena run --game <id> --models <id>,<id>,...` is the first
  and for now the only way to start a match with real models. Each named
  model from `config/models.yaml` takes one seat, in order. The command
  builds one `Budget` for the match, so it needs `DATABASE_URL`; it records
  the match and its events in the same tables as the API. When a cost cap
  is reached it does not ask: the match is closed as `interrupted` and the
  command exits with 3. After the match it prints what each seat cost from
  the ledger and checks that the stored log rebuilds the final state;
  `--save FILE` writes seats, result, cost and all events as JSON. Which
  model sat where is in the ledger rows and in the saved file, not in the
  event log.
- **Why:** The first real matches are run by hand, one at a time, by whoever
  holds the key, and a command in a terminal is the smallest thing that
  does that with the caps in force. A match that stops at a cap cannot
  overrun while nobody watches. The API keeps seating bots only until the
  UI can show a pause and ask.
- **Alternatives:** Model seats in `POST /matches` first (needs the pause
  question in the UI and a way to keep a key out of requests); a script
  outside the package (would not be tested with the rest); raising the cap
  from a prompt in the terminal (a second way to spend that tests cannot
  cover).

## D-071 · One forced tool call carries the thought and the move; reasoning is kept short

- **Date:** 2026-11-11
- **Decision:** This replaces the answer format of the agent decision (text
  is the thought, the tool call is the move) for what goes to a model:
  - Every call is sent with `tool_choice: required`.
  - Every tool gets a first argument `thought`, added where the tools are
    described for the model (`tool_schemas`). The agent runner takes it out
    and logs it as the thought; a game never sees it, and a game tool with an
    argument of that name is refused. Text beside the call is still the
    thought when the argument is empty or missing.
  - Every call carries `reasoning_effort` from `limits.reasoning_effort` in
    `config/models.yaml`, set to `low`. When an answer has no text of its
    own, the model's reasoning is its text.
  - A reply knows whether it ran into the output limit (`ModelReply.cut_off`);
    such a reply without a tool call is told that it was cut off and to be
    brief. The output limit stays at 1500 tokens.
  - A request that a provider refuses (400, 404 or 422) while it carries
    these options is sent once more without them. Only if that is refused
    too does the seat lose its model. In a test of all eight roster models
    one refused the options outright, and another, served by several
    providers, took them in one match and refused them in the next.
    The budget has booked that call once, at its upper bound; the second
    request goes out under the same booking. That holds only because a
    refused request is not billed, so at most one of the two costs money.
    The set of statuses must therefore never grow to one a provider may bill.
- **Why:** Two real matches with the cheapest models of the roster. In the
  first (Liar's Deck, four models) 83 of 130 answers were rejected and 18
  turns went to the random fallback: two reasoning models spent the whole
  output limit thinking in 73 of 87 calls, and that thinking was 90 % of the
  output tokens paid for. With `reasoning_effort: low` (Poker, six models)
  those two were clean and calls were three times faster, but 30 of 138
  answers were still rejected: two other models answered in prose or wrote
  the call as text. Asking for text and a tool call in one answer is more
  than several of these models do; one call that holds both is what all of
  them can do, and it is one model call per move, which is also the cheapest.
- **Alternatives:** A higher output limit (pays for more of the same); a
  separate `think` tool as in the spec (a second call per move); thoughts
  only from models that write text beside a call (most cheap ones do not);
  parsing calls out of prose (guesswork per model); dropping the models that
  failed (they are among the cheapest).

## D-072 · Replays: one event per step, the board from the API, the step in the address

- **Date:** 2026-11-11
- **Decision:**
  - A replay steps through the stored log one event at a time: step N shows the
    first N events (0 is before the match, the log length its end). Opened
    without a step, a replay shows the whole match.
  - The board of a step comes from `GET /matches/{id}/board?events=N`, which
    replays that prefix and returns the game's `render_spec`. The player loads
    it through the web server, keeps every board it has seen and leaves the last
    one up while the next loads. The columns are the live view's, through one
    shared component (`MatchColumns`).
  - Play advances one step per tick (0.5× to 4×, 1000 to 125 ms) and stops at
    the end. The step is kept in the address (`?step=N`, without a new history
    entry), so a copied address or the share link opens the same place.
  - `GET /replays` lists the newest 100 finished matches with their winners
    (rank 1) and the cost of their model calls, in one query. Failed, aborted
    and interrupted matches are not replays.
  - The JSON export (`/replays/<id>/export.json`, format
    `aigameversus-replay/1`) is the match record, its cost and the whole log as
    spectators see it, thoughts and hidden cards included; replaying the log
    rebuilds the match.
- **Why:** The event is the smallest unit the log has, so no step hides
  anything; the board stays the plugin's drawing, never rebuilt in the browser.
- **Alternatives:** steps per turn (the log has no turn marker every game
  shares); boards for all steps at once (hundreds of replays per load);
  exporting only public events.

## D-073 · Relationships: trust from facts each player saw, rules as data

- **Date:** 2026-11-11
- **Decision:**
  - After a rated match the server adds its facts to the relationships of the
    seated profiles (`relationships`, `remembered_matches`, migration `0008`),
    once per match id, in one transaction. A memory problem never fails the
    match or its rating.
  - A fact is one player's view of another (`arena/memory/facts.py`) and is
    read only from the game events that player could see: public ones and
    those sent to them. Thoughts and spectator-only events are never read.
  - Facts today: Liar's Deck: caught lying, accused me falsely, told the truth
    when I called; Poker: bet or raised and lost every pot of the showdown (the
    stats' bluff rule); Werewolf: packmate, turned out to be a wolf (the seer's
    check, or the role shown at death; once per wolf), voted against me, voted
    against me though we were lovers.
  - What each fact is worth and its note are in `config/memory/trust.yaml`.
    A match sums its facts per pair, then trust is clamped to -100..+100.
    A pair keeps its 10 newest notes, newest first.
  - `GET /profiles/{id}/relations` lists the others, strongest feeling
    first; the profile page shows them as a trust list. `relations` left the
    profile response.
- **Why:** Facts from the observer's own view cannot leak hidden roles or
  cards. Rules as data can be tuned without code, as rule 7 asks.
- **Alternatives:** trust from the whole log (the seer's checks would reach
  every player); decay over time (not in the spec); notes for every match
  without a cap.

## D-076 · The monthly cap is 25 euros

- **Date:** 2026-11-11
- **Decision:** `limits.month_eur` in `config/models.yaml` is 25.00 (it was
  5.00, D-001). The cap per match stays 0.50 EUR. Whatever is above 25 EUR a
  month still pauses a match, as before.
- **Why:** The project owner set it after the first real matches (six
  matches, 0.18 EUR together): he wants stronger models and research runs,
  which a 5 EUR month would stop early. He kept the per-match cap; a single
  research run may get a larger budget only when that is set for the run
  (a per-run budget is still to be built).
- **Alternatives:** No monthly cap (one runaway batch could spend without
  limit); a higher cap per match for everyone (a mistake would cost more).

## D-077 · A game card starts a match only when the arena has the game

- **Date:** 2026-11-11
- **Decision:** A home card links to the new-match form with its game chosen
  (`/matches/new?game=<id>`) only when `GET /games` lists the game; otherwise
  it says "Coming soon" and has no link. Throne of Tokens therefore turns
  active by itself when its plugin is installed. The form reads `?game=`
  as its first choice.
- **Why:** A card that leads to a form which cannot start the game is a dead
  end; the arena's game list is the one source of what can be played.
- **Alternatives:** a hard-coded "coming soon" flag per card (needs a code
  change when a plugin lands); hiding the card (the game should still be
  announced).

## D-078 · One transcript renders every match for every reader

- **Date:** 2026-11-11
- **Decision:** `arena/transcript/` turns the events of a match into readable
  lines, one per event, in English and German (`TranscriptLine`: `kind`, `actor`,
  `text`, `detail`, `importance`, `raw`). Each game has a renderer class with a
  `handle_<type>` method per event type; the engine's own events are handled once
  in the base class. A test reads the plugins' source and fails when one emits a
  type without a method. Hidden information (hands, roles, private choices,
  thoughts, whispers, the seed) is written only with `spoilers=True`; public talk
  always. `importance` is 1 for bookkeeping, 2 normal, 3 highlight; `kind` is one of
  heading, action, speech, whisper, thought, reveal, result, narration, info.
  It is served by `GET /matches/{id}/transcript?lang=&spoilers=&format=json|text|markdown`
  and printed by `arena run` (live, instead of raw events; `--raw` keeps them) and
  `arena transcript <match-id|file>`. Players are "Name (model)" where the match
  was rated or a file names its seats, else the seat id. The Werewolf narrator's own
  lines are shown only in the language the match was played in, as bookkeeping.
- **Why:** The live view, replays, exports and the terminal need the same words
  or they drift apart; one renderer per game, tested against what the plugins emit,
  keeps them equal. Keeping the raw event on each line lets a UI fold it away
  without a second request.
- **Alternatives:** a formatter in TypeScript for the web (a second copy to keep
  in step, and no help for the CLI); text written by the plugins themselves (puts
  words into rules code, and names are a presentation matter).

## D-080 · The spectator UI: one watch screen, the transcript as its only text, two viewer modes

- **Date:** 2026-11-11
- **Decision:** `docs/UI-DESIGN.md` sets the look. Live view and replay become
  one "watch" screen: the board as a large stage, one commentary column built
  from `TranscriptLine` (`kind`, `importance`), and a timeline with chapters
  and highlight markers. There are two named viewer modes: "Spectator view"
  (the default: thoughts, hands and roles visible) and "Spoiler-free". In
  spoiler-free mode the transcript is fetched with `spoilers=false`. The web
  server strips spectator-only events and the secret board fields before they
  reach the browser, and there is no seed and no export.
- **Why:** The audit (screenshots of the bot demo at 375 and 1280) found raw
  engine lines, three equal columns with a small board, pages 11–17k px tall on
  mobile, and replays without rounds or highlights. One text source keeps the
  CLI, the API and the UI from telling a match in different words.
- **Alternatives:** Keep three equal columns and polish them (keeps the board
  small); a formatter in the browser (a second wording to keep in sync); hide
  thoughts by default (hides the project's main attraction).

## D-081 · A model has one rating profile, whatever seat it sits in

- **Date:** 2026-11-11
- **Decision:** A finished `arena run --models` match is rated. Each model gets
  one profile per personality (`RatingStore.model_profile`; the id derives from
  model id and personality, so it is the same in every match and every seat; no
  personality is chosen from the command line yet). Its rating, statistics and
  cost therefore add up across matches. A profile is rated once per match, so a
  match with the same model in several seats is left unrated and the command says
  so. Random bots keep one profile per seat, as the log needs a seat per profile
  (D-052); the leaderboard groups them by kind when it shows them.
- **Why:** The leaderboard compares models, not seats: a model that sat in seat 3
  yesterday and seat 1 today is the same player. Rating the same profile twice in
  one match would break the match's placements.
- **Alternatives:** rating the model's best seat, or splitting its placements
  (arbitrary); one profile per model and seat (the old way: no comparison).
## D-082 · Model seats in POST /matches, off by default and confirmed per match

- **Date:** 2026-11-11
- **Decision:** `POST /matches` takes `models` (model ids, one per seat) and
  then plays those seats behind one `Budget`, like `arena run --models`. The
  server refuses model seats unless it was started with
  `ARENA_ALLOW_MODEL_SEATS=1`, the request must carry `confirm_spend: true`,
  and the provider's key must be set; otherwise nothing is recorded or sent.
  A cost cap ends the match as `interrupted`. Model matches are not rated yet.
  Every match records who sat where (`seats`: name, model id, kind) and
  whether it was played here or imported (`origin`).
- **Why:** The project owner wants to start and watch real matches from the
  UI. The API has no login and listens on localhost, so anything on the
  machine could start paid matches: off by default plus an explicit flag per
  request keeps a mistake from spending. Seats with names are what viewers
  read instead of p1..pN.
- **Alternatives:** Authentication (a bigger change, not needed on loopback
  yet); model seats always on (any local script could spend); a separate
  table for seats (the record is read with the match anyway).

## D-083 · The prompt names the player's own seat where the model reads it

- **Date:** 2026-11-11
- **Decision:** Besides the first line of the system message, the prompt now
  says once more that every mention of the seat is the player, ends the ask
  with "You are p8.", and starts every event line that the player did (its
  `player`, `caller` or `from` is the reader) with `[you]`. Events that only name the reader in
  another field (a vote against them) are not marked: the player did not do
  them. Other players' words stay as they were written.
- **Why:** In the first real Werewolf match the seer (seat p8) wrote about
  "p7 and p8" as if they were others, attacked its own seer claim in public
  and tried to vote for itself; another model called its own seat suspicious
  in its thought. Both had read their seat once, at the top of a long
  prompt, and then met it many times as a plain id among other ids.
- **Alternatives:** Names instead of seat ids (needs player info in every
  game's events, planned for the UI); rewriting other players' words to say
  "you" (would change what was said); marking every event that names the
  reader anywhere (marks votes against the player as theirs).

## D-093 · The runner takes the prompt version from the match settings

- **Date:** 2026-11-11
- **Decision:** `ModelAgent` gets the match settings. It asks the game for
  `rules(settings)` once and for `situation_summary(observation, settings)`
  every turn, and puts the summary in a `<summary>` block above
  `<situation>`; the system message then names that block too. The match
  records `prompt_version(settings)` in `match_started`, and `arena run
  --save` writes it into the export. Without a summary the prompt is the one
  from before, byte for byte (the p1 golden files check it).
- **Why:** Poker and Werewolf have a second prompt version (new rules, a
  summary of the turn), and an A/B comparison needs every match to say which
  one its models read. The summary comes first because models read the top
  and the end of a prompt most closely; it is built from the observation, so
  it cannot leak what the player may not see.
- **Alternatives:** The summary inside `<situation>` (mixes text with the
  JSON a mock model parses); the version only in the settings (a default
  would not show up in the log, and the default may change); a summary in
  the system message (that one is meant to be the server's words, not game
  data).

## D-097 · The leaderboard ranks models; random bots are one row

- **Date:** 2026-11-11
- **Decision:** `GET /leaderboard` takes `kind=models|bots|all`. Without it, real
  models are shown, or everyone when no model is rated yet (`fallback: true`);
  `counts` gives the rows per kind. The per-seat profiles of random bots ("Random
  Bot p3", D-052) are grouped into one "Random Bot" row with their ratings,
  win rates and placements averaged by games played (`members` says how many
  seats); `group_bots=false` lists every seat, for tests and the profile pages.
  Each row also has the vendor (from `config/models.yaml`), the average cost of
  one rated game (the ledger's booked calls of the profile's seats over its
  rated games) and the tool-error rate: refused answers over all answers
  (`action_rejected` / (`action_accepted` + `action_rejected`) of its seats).
  The web page filters by kind and keeps the game tab.
- **Why:** The board compares models; a bot has no identity beyond its kind, and
  a per-kind profile cannot hold several seats of one match (a profile is rated
  once per match), so the grouping is done where the board is read.
- **Alternatives:** one stored profile per bot kind (impossible with several bot
  seats per match); hiding bots altogether (the demo needs them).
