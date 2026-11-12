# Decisions

Decisions taken where [DESIGN.md](DESIGN.md) is open, or where this project
deliberately differs from it. `DESIGN.md` is kept as the original spec, apart
from the author line and the game title (D-018); where the two disagree, the
decision wins.

Each decision is its own file in [decisions/](decisions/): date, decision, why,
alternatives considered. Numbers are `D-001` and up, never reused.

**To add one:** claim the next free number in the team's number list, then
`python scripts/decisions.py new D-0NN "Title"`, fill in the file, and keep the
line it added to the list below. Do not write decisions into this file: a
leftover `## D-0NN · Title` block here fails `tests/test_decisions.py`; move it
with `python scripts/decisions.py adopt`.

- [D-001](decisions/D-001-answers-to-the-spec-s-open-questions.md) · Answers to the spec's open questions
- [D-002](decisions/D-002-host-ports-8100-3100-5433-6380-bound-to-127-0-0-1.md) · Host ports 8100 / 3100 / 5433 / 6380, bound to 127.0.0.1
- [D-003](decisions/D-003-no-restart-policy-in-compose.md) · No restart policy in Compose
- [D-004](decisions/D-004-uv-with-a-lockfile-hatchling-ruff.md) · uv with a lockfile, hatchling, ruff
- [D-005](decisions/D-005-static-web-placeholder-until-phase-5.md) · Static web placeholder until phase 5
- [D-006](decisions/D-006-worker-placeholder-with-a-heartbeat-healthcheck.md) · Worker placeholder with a heartbeat healthcheck
- [D-007](decisions/D-007-secret-scan-with-a-pinned-gitleaks-image.md) · Secret scan with a pinned gitleaks image
- [D-008](decisions/D-008-pinned-service-images-postgresql-18-redis-8-nginx-1-30.md) · Pinned service images: PostgreSQL 18, Redis 8, nginx 1.30
- [D-009](decisions/D-009-plugins-change-state-only-through-events.md) · Plugins change state only through events
- [D-010](decisions/D-010-named-random-streams-derived-from-the-seed.md) · Named random streams derived from the seed
- [D-011](decisions/D-011-validation-order-and-fallback.md) · Validation order and fallback
- [D-012](decisions/D-012-one-engine-loop-for-all-turn-modes-one-action-per-request.md) · One engine loop for all turn modes, one action per request
- [D-013](decisions/D-013-high-card-as-a-shipped-reference-game.md) · High Card as a shipped reference game
- [D-014](decisions/D-014-asyncpg-and-sql-migration-files-no-orm.md) · asyncpg and SQL migration files, no ORM
- [D-015](decisions/D-015-the-log-is-stored-once-per-turn-and-replay-is-strict-about.md) · The log is stored once per turn, and replay is strict about versions
- [D-016](decisions/D-016-event-data-is-plain-json-enforced-at-emit.md) · Event data is plain JSON, enforced at emit
- [D-017](decisions/D-017-database-tests-use-a-real-postgres-one-schema-per-test.md) · Database tests use a real Postgres, one schema per test
- [D-018](decisions/D-018-the-bluff-card-game-is-called-liar-s-deck.md) · The bluff card game is called Liar's Deck
- [D-019](decisions/D-019-throne-of-tokens-data-layout-and-loader.md) · Throne of Tokens data: layout and loader
- [D-020](decisions/D-020-throne-of-tokens-values-the-spec-leaves-open.md) · Throne of Tokens values the spec leaves open
- [D-021](decisions/D-021-liar-s-deck-devil-card-is-one-of-the-jokers.md) · Liar's Deck devil card is one of the jokers
- [D-022](decisions/D-022-werewolf-role-selection-wolf-count-and-balance-light.md) · Werewolf role selection: wolf count and balance light
- [D-023](decisions/D-023-werewolf-klassisch-scales-its-wolves-with-the-table.md) · Werewolf "Klassisch" scales its wolves with the table
- [D-024](decisions/D-024-an-agent-answers-with-one-action-and-a-thought-thoughts-are.md) · An agent answers with one action and a thought; thoughts are an engine channel
- [D-025](decisions/D-025-the-turn-clock-is-in-the-engine-and-an-agent-that-gives-up.md) · The turn clock is in the engine, and an agent that gives up loses its seat
- [D-026](decisions/D-026-one-model-call-boundary-the-runner-retries-the-mock-llm.md) · One model-call boundary; the runner retries; the mock LLM stands behind it
- [D-027](decisions/D-027-prompt-layout-and-how-other-players-words-are-kept-apart.md) · Prompt layout, and how other players' words are kept apart from instructions
- [D-028](decisions/D-028-what-an-agent-writes-is-made-storable-before-it-is-logged.md) · What an agent writes is made storable before it is logged
- [D-029](decisions/D-029-a-game-s-title-and-rules-text-each-live-in-one-place.md) · A game's title and rules text each live in one place
- [D-030](decisions/D-030-spectator-ui-sveltekit-3-on-node-api-calls-server-side.md) · Spectator UI: SvelteKit 3 on Node, API calls server-side, English chrome
- [D-031](decisions/D-031-multiplayer-elo-the-overall-rating-and-rating-storage.md) · Multiplayer Elo, the overall rating, and rating storage
- [D-032](decisions/D-032-leaderboard-per-match-placements-demo-seed-display-rules.md) · Leaderboard: per-match placements, demo seed, display rules
- [D-033](decisions/D-033-liar-s-deck-engine-turns-talk-thoughts-and-open-rules.md) · Liar's Deck engine: turns, talk, thoughts and open rules
- [D-034](decisions/D-034-money-is-counted-per-model-call-in-a-ledger-before-the-call.md) · Money is counted per model call, in a ledger, before the call is sent
- [D-035](decisions/D-035-at-a-cap-the-match-pauses-the-turn-is-dropped-and-played.md) · At a cap the match pauses: the turn is dropped and played again later
- [D-036](decisions/D-036-config-models-yaml-limits-and-prices-next-to-the-roster.md) · `config/models.yaml`: limits and prices next to the roster
- [D-037](decisions/D-037-litellm-s-own-logger-is-switched-off.md) · LiteLLM's own logger is switched off
- [D-038](decisions/D-038-poker-betting-minimum-raise-short-all-ins-side-pots-odd.md) · Poker betting: minimum raise, short all-ins, side pots, odd chips
- [D-039](decisions/D-039-poker-tournament-button-dealing-duplicate-mode-statistics.md) · Poker tournament: button, dealing, duplicate mode, statistics
- [D-040](decisions/D-040-a-match-has-a-turn-limit.md) · A match has a turn limit
- [D-041](decisions/D-041-a-game-is-found-by-its-folder.md) · A game is found by its folder
- [D-042](decisions/D-042-matches-from-the-api-run-inside-the-api-process-spectators.md) · Matches from the API run inside the API process; spectators read the log over WebSocket
- [D-043](decisions/D-043-the-arena-command-plays-in-its-own-process.md) · The `arena` command plays in its own process
- [D-044](decisions/D-044-a-game-reads-nothing-from-the-order-of-keys-in-event-data.md) · A game reads nothing from the order of keys in event data
- [D-045](decisions/D-045-turn-limits-of-poker-and-liar-s-deck-are-upper-bounds-from.md) · Turn limits of Poker and Liar's Deck are upper bounds from the rules
- [D-046](decisions/D-046-werewolf-engine-step-queue-night-order-deaths-and-wins.md) · Werewolf engine: step queue, night order, deaths and wins
- [D-047](decisions/D-047-werewolf-day-captain-narrator-and-language.md) · Werewolf day: captain, narrator and language
- [D-048](decisions/D-048-throne-of-tokens-map-rows-of-hexes-start-regions-from-data.md) · Throne of Tokens map: rows of hexes, start regions from data, land in one piece
- [D-049](decisions/D-049-fog-of-war-a-nation-sees-what-is-in-range-now-by-distance.md) · Fog of war: a nation sees what is in range now, by distance alone
- [D-050](decisions/D-050-werewolf-roles-batch-a-lovers-protector-little-girl-elder.md) · Werewolf roles batch A: lovers, Protector, Little Girl, Elder, Idiot, Scapegoat
- [D-051](decisions/D-051-werewolf-roles-batch-b-raven-wild-child-prime-wolf-white.md) · Werewolf roles batch B: Raven, Wild Child, Prime Wolf, White Werewolf, Bear
- [D-052](decisions/D-052-a-finished-api-match-rates-its-random-bots.md) · A finished API match rates its random bots
- [D-053](decisions/D-053-per-game-statistics-are-pure-functions-over-the-event-log.md) · Per-game statistics are pure functions over the event log
- [D-054](decisions/D-054-poker-statistics-definitions.md) · Poker statistics: definitions
- [D-055](decisions/D-055-werewolf-statistics-definitions.md) · Werewolf statistics: definitions
- [D-056](decisions/D-056-throne-of-tokens-economy-one-stock-per-nation-and-what-the.md) · Throne of Tokens economy: one stock per nation, and what the spec leaves open about cities
- [D-057](decisions/D-057-throne-of-tokens-state-one-model-systems-that-emit-events.md) · Throne of Tokens state: one model, systems that emit, events that carry outcomes
- [D-058](decisions/D-058-match-controls-pause-between-turns-abort-as-its-own-status.md) · Match controls: pause between turns, abort as its own status
- [D-061](decisions/D-061-werewolf-dusterwald-mix-scales-its-wolves-chaos-stays-as-it.md) · Werewolf "Düsterwald-Mix" scales its wolves; "Chaos" stays as it is
- [D-062](decisions/D-062-the-chronicler-tells-a-finished-match-from-templates-behind.md) · The chronicler tells a finished match from templates, behind a Narrator
- [D-063](decisions/D-063-profile-statistics-seats-stored-at-rating-time-totals-read.md) · Profile statistics: seats stored at rating time, totals read from the logs
- [D-064](decisions/D-064-live-view-sse-relay-on-the-web-server-a-generic-board.md) · Live view: SSE relay on the web server, a generic board, spoilers in the UI
- [D-065](decisions/D-065-new-match-form-bot-seats-now-models-and-cost-limit-shown-for.md) · New-match form: bot seats now, models and cost limit shown for later
- [D-066](decisions/D-066-werewolf-role-selection-in-the-new-match-form.md) · Werewolf role selection in the new-match form
- [D-067](decisions/D-067-game-tables-are-components-chosen-by-the-render-spec-layout.md) · Game tables are components chosen by the render_spec layout
- [D-068](decisions/D-068-the-poker-spectator-spec-carries-side-pots-and-win-chances.md) · The Poker spectator spec carries side pots and win chances
- [D-069](decisions/D-069-the-werewolf-circle-draws-votes-from-the-log-and-shows-no.md) · The Werewolf circle draws votes from the log and shows no model names
- [D-070](decisions/D-070-real-models-take-their-seats-from-the-command-line-first.md) · Real models take their seats from the command line first
- [D-071](decisions/D-071-one-forced-tool-call-carries-the-thought-and-the-move.md) · One forced tool call carries the thought and the move; reasoning is kept short
- [D-072](decisions/D-072-replays-one-event-per-step-the-board-from-the-api-the-step.md) · Replays: one event per step, the board from the API, the step in the address
- [D-073](decisions/D-073-relationships-trust-from-facts-each-player-saw-rules-as-data.md) · Relationships: trust from facts each player saw, rules as data
- [D-075](decisions/D-075-match-memories-the-memory-block-memory-off-and-reset.md) · Match memories, the memory block, memory off and reset
- [D-076](decisions/D-076-the-monthly-cap-is-25-euros.md) · The monthly cap is 25 euros
- [D-077](decisions/D-077-a-game-card-starts-a-match-only-when-the-arena-has-the-game.md) · A game card starts a match only when the arena has the game
- [D-078](decisions/D-078-one-transcript-renders-every-match-for-every-reader.md) · One transcript renders every match for every reader
- [D-080](decisions/D-080-the-spectator-ui-one-watch-screen-the-transcript-as-its-only.md) · The spectator UI: one watch screen, the transcript as its only text, two viewer modes
- [D-081](decisions/D-081-a-model-has-one-rating-profile-whatever-seat-it-sits-in.md) · A model has one rating profile, whatever seat it sits in
- [D-082](decisions/D-082-model-seats-in-post-matches-off-by-default-and-confirmed-per.md) · Model seats in POST /matches, off by default and confirmed per match
- [D-083](decisions/D-083-the-prompt-names-the-player-s-own-seat-where-the-model-reads.md) · The prompt names the player's own seat where the model reads it
- [D-084](decisions/D-084-throne-of-tokens-armies-movement-training-and-what-a-settler.md) · Throne of Tokens armies: movement, training, and what a settler may do
- [D-086](decisions/D-086-the-watch-screen-spoiler-free-by-allowlist-in-the-web-server.md) · The watch screen: spoiler-free by allowlist in the web server, playback by moments
- [D-087](decisions/D-087-prompts-have-versions-a-game-s-rules-and-summary-per-prompt.md) · Prompts have versions: a game's rules and summary per `prompt_version`
- [D-090](decisions/D-090-experiments-are-registered-as-files-before-their-first-paid.md) · Experiments are registered as files before their first paid match
- [D-091](decisions/D-091-the-launch-form-seats-models-all-or-none-a-spend-box-the.md) · The launch form seats models: all or none, a spend box, the month in view
- [D-093](decisions/D-093-the-runner-takes-the-prompt-version-from-the-match-settings.md) · The runner takes the prompt version from the match settings
- [D-095](decisions/D-095-the-spend-ledger-in-a-database-of-its-own-the-key-in-a-file.md) · The spend ledger in a database of its own, the key in a file
- [D-097](decisions/D-097-the-leaderboard-ranks-models-random-bots-are-one-row.md) · The leaderboard ranks models; random bots are one row
- [D-098](decisions/D-098-a-model-page-is-the-profile-of-a-model-without-a-personality.md) · A model page is the profile of a model without a personality
- [D-099](decisions/D-099-key-moments-are-staged-by-the-watch-screen-from-the.md) · Key moments are staged by the watch screen, from the transcript's highlights
- [D-100](decisions/D-100-a-finished-match-ends-on-a-result-card-showdowns-and-the.md) · A finished match ends on a result card; showdowns and the final ranking are structured
- [D-101](decisions/D-101-an-estimate-before-a-match-bots-play-it-the-prompts-are.md) · An estimate before a match: bots play it, the prompts are measured
- [D-102](decisions/D-102-any-openrouter-model-that-can-call-tools-may-take-a-seat.md) · Any OpenRouter model that can call tools may take a seat
- [D-103](decisions/D-103-a-seat-s-identity-comes-from-the-match-record-first-a-model.md) · A seat's identity comes from the match record first; a model seat never reads as a bot
- [D-104](decisions/D-104-one-display-name-per-seat-computed-by-the-server-never-the.md) · One display name per seat, computed by the server, never the seat id
- [D-105](decisions/D-105-the-launch-form-picks-a-model-per-seat-from-the-whole.md) · The launch form picks a model per seat from the whole catalog
- [D-106](decisions/D-106-match-analytics-a-pure-function-of-the-log-public-events.md) · Match analytics: a pure function of the log, public events only without spoilers
- [D-107](decisions/D-107-the-analytics-tab-draws-the-arena-s-numbers-with-its-own.md) · The Analytics tab draws the arena's numbers with its own small SVG charts
- [D-108](decisions/D-108-every-model-move-says-what-it-took-in-a-spectators-only.md) · Every model move says what it took, in a spectators-only event
- [D-109](decisions/D-109-seat-ids-in-the-players-own-words-are-shown-as-name-chips.md) · Seat ids in the players' own words are shown as name chips
- [D-110](decisions/D-110-matches-play-out-at-reading-pace-live-and-in-replays.md) · Matches play out at reading pace, live and in replays, whatever the models' speed
- [D-111](decisions/D-111-a-model-may-set-its-own-call-options-rate-limits-are-waited.md) · A model may set its own call options; rate limits are waited out longer, within a budget
- [D-113](decisions/D-113-refused-answers-are-answer-quality-a-retry-marker-on-the.md) · Refused answers are answer quality: a retry marker on the move, red only for a random move
- [D-114](decisions/D-114-a-garbled-tool-call-that-clearly-means-one-move-is-repaired.md) · A garbled tool call that clearly means one move is repaired, and the move says so
- [D-115](decisions/D-115-the-werewolf-circle-is-a-stage-the-newest-speech-in-the.md) · The Werewolf circle is a stage: the newest speech in the middle, deaths turn the role over
- [D-116](decisions/D-116-throne-of-tokens-is-played-with-one-call-per-nation-and.md) · Throne of Tokens is played with one call per nation and round, and a broken order is dropped, not the call
- [D-117](decisions/D-117-a-headline-for-viewers-is-a-match-flag-thought-headline-not.md) · A headline for viewers is a match flag, thought_headline, not a prompt version
- [D-118](decisions/D-118-cut-off-answers-and-rate-limits-are-counted-apart-and-a.md) · Cut-off answers and rate limits are counted apart, and a model is qualified per route, game and configuration
- [D-119](decisions/D-119-werewolf-p4-whole-match-strategy-text-liar-s-deck-p1-stays.md) · Werewolf p4 whole-match strategy text; Liar's Deck p1 stays frozen with a known defect
- [D-120](decisions/D-120-free-variants-are-left-out-of-the-catalog-and-every-model.md) · Free variants are left out of the catalog, and every model says how reliably it has played here
- [D-121](decisions/D-121-p1-1-says-where-the-thought-goes-as-the-system-message-does.md) · p1.1 says where the thought goes as the system message does; p1 stays the baseline
- [D-122](decisions/D-122-table-talk-is-checked-against-the-engine-s-cards-and-roles.md) · Table talk is checked against the engine's cards and roles, by rule
- [D-123](decisions/D-123-jev.md) · Jev calibration preserves intent and separates human agreement from ground truth
- [D-124](decisions/D-124-the-throne-of-tokens-board-draws-the-hex-map-in-svg-with-a.md) · The Throne of Tokens board draws the hex map in SVG, with a nation's fog on request
- [D-125](decisions/D-125-jev-repairs-a-broken-call-only-into-a-legal-move-the-model.md) · Jev repairs a broken call only into a legal move the model meant, above a threshold, never otherwise
- [D-126](decisions/D-126-throne-of-tokens-combat-what-a-battle-costs-the-ranged-round.md) · Throne of Tokens combat: what a battle costs, the ranged round, and which city is a capital
- [D-127](decisions/D-127-when-a-werewolf-scene-ends-the-game-master-s-line-takes-the.md) · When a Werewolf scene ends, the game master's line takes the stage until someone speaks
- [D-128](decisions/D-128-the-throne-of-tokens-scoreboard-is-public-by-rule-positions.md) · The Throne of Tokens scoreboard is public by rule; positions and contents stay fogged
- [D-129](decisions/D-129-a-repaired-move-carries-a-muted-marker-per-tier-spoiler-free.md) · A repaired move carries a muted marker per tier; spoiler-free shows the tier and probability only
- [D-130](decisions/D-130-throne-of-tokens-is-played-round-by-round-in-one-call-per.md) · Throne of Tokens is played round by round in one call per nation
- [D-131](decisions/D-131-under-the-werewolf-circle-who-claims-what-and-who-suspects.md) · Under the Werewolf circle: who claims what and who suspects whom, cut at the moment on screen
- [D-132](decisions/D-132-a-model-is-qualified-per-configuration-by-its-first-answers.md) · A model is qualified per configuration by its first answers to real turns of seeded bot matches
- [D-133](decisions/D-133-throne-of-tokens-has-one-setting-rounds-for-a-shorter-match.md) · Throne of Tokens has one setting, rounds, for a shorter match
