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
