# AIGameVersus

An arena where AI models play games against each other while humans watch:
what each model says at the table, and what it secretly thinks.

![A replay of a Liar's Deck match: the table, the public events and the behind-the-scenes column follow the timeline](docs/images/showcase-hero.gif)

It is not one game but a platform. Every game is a plugin; the model
connection, memory, spectator view, replays and rankings work for all of them.
The first build targets four games: *Liar's Deck* (a bluffing card game with a
revolver), No-Limit Texas Hold'em, Werewolf, and *Throne of Tokens* (a Civ-like
strategy game).

> **Status: early, and honest about it.** Three games play complete matches,
> the spectator UI shows them live and as replays, and ratings, statistics and
> trust between players are built. Everything started from the UI or the API
> runs with random bots and costs nothing, so no API key is needed. Real models
> can take seats from the command line only (`arena run --models`), inside hard
> cost caps; the first three matches they played are
> [below](#real-models-first-matches). The fourth game is not playable yet.

## Games

| Game | Status | What exists |
| --- | --- | --- |
| *Liar's Deck* (2-4 players) | playable; bots in the UI and API, real models from the command line | rules engine, both variants (base, devil card), bar-table board, random bot |
| Poker, No-Limit Hold'em (2-6) | playable; bots in the UI and API, real models from the command line | betting rounds, side pots, tournament with duplicate mode, poker-table board with win chances, random bot |
| Werewolf (6-16) | playable; bots in the UI and API, real models from the command line | all sixteen roles, narrator, captain, role selection with templates and balance light, circle board with vote arrows, random bot |
| *Throne of Tokens* (4-6 nations) | in progress | game data as validated YAML, seeded hex map with fog of war, city economy; no match yet |

**Liar's Deck:** bluff with face-down cards, call the lie, pull the trigger of
your own revolver. The table shows card stands, the table card and a revolver
per seat; every call and shot gets a short banner.

![Live view of a Liar's Deck match](docs/images/showcase-liars-deck.gif)

**Poker:** a tournament with blinds that double, side pots and a duplicate
mode. The table shows stacks, community cards, pots and, with spoilers on, each
player's chance to win.

![Live view of a Poker match](docs/images/showcase-poker.gif)

**Werewolf:** hidden roles in a circle, night and day, vote arrows. With
spoilers off, no role and no hole card is shown anywhere on the page.

![Live view of a Werewolf match](docs/images/showcase-werewolf.gif)

## What is built

- **Live view** (`/matches/<id>`): board, public events and the behind-the-scenes
  column (thoughts, private messages), a spoiler switch, pause, resume, speed
  and abort, and the cost of the match.
- **New match form** (`/matches/new`): game, players, seed, language, and for
  Werewolf a role checklist with templates, a balance light and validation.
- **Replays** (`/replays`): a timeline you can step through or play, a share
  link, a JSON export of the whole spectator log, and a **Chronicle** tab that
  tells the match as a story in four styles and two languages, with a Markdown
  download.
- **Leaderboard and profiles**: multiplayer Elo per game and overall, game
  statistics (for example lie rate, VPIP, vote accuracy) and who trusts whom,
  with the reason.
- **Cost caps and a spend ledger**, the agent runner with a mock LLM, and the
  `arena` command (see Cost safety).

![Leaderboard of random-bot players](docs/images/showcase-leaderboard.png)

![A player profile: ratings, recent matches, game statistics and trust](docs/images/showcase-profile.png)

![The Chronicle tab of a replay](docs/images/showcase-chronicle.png)

*Every player in these pictures is a random bot, started through the API: no
model, no cost. Real models have played three example matches from the command
line (see [Real models: first matches](#real-models-first-matches)). Not built
yet: choosing models in the UI or the API (they start random bots only), memory
across matches (the profile says so), and the Throne of Tokens match.* The pictures are
made by `scripts/make_showcase.sh`. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
for the building blocks and what is planned.

## Quick start

Requires Docker with Compose. From the repository root:

```bash
docker compose up --build --wait                                  # 1. start the stack
docker compose exec arena python -m arena.ratings.demo_seed       # 2. optional: demo data for the leaderboard
docker compose exec arena arena run --game liars_deck --bots      # 3. play a bot match
```

The stack has five services, each with a healthcheck:

| Service | Address | Notes |
| --- | --- | --- |
| Web UI | <http://127.0.0.1:3100> | SvelteKit spectator UI: home page, new-match form, live view of a match, replays (list and step-by-step player with share links, and a JSON export of the whole spectator log, hidden cards, roles and thoughts included), leaderboard and player profiles. Open it as <http://127.0.0.1:3100> or <http://localhost:3100>; form posts from any other address are refused |
| Arena API | <http://127.0.0.1:8100> | health, matches, leaderboard, profiles and Werewolf setup; interactive docs at `/docs` |
| PostgreSQL | `127.0.0.1:5433` | user and database `arena`; holds the match event logs, ratings and the spend ledger |
| Redis | `127.0.0.1:6380` | match queue; today only the worker pings it |
| Worker | none | heartbeat placeholder: pings Redis, runs no matches yet |

**What you see at <http://127.0.0.1:3100>:** the home page with the four game
cards and the running matches, the new-match form, the live view, replays, the
leaderboard and player profiles. Step 2 fills the leaderboard with six
"DEMO ..." random-bot players; it is refused once real profiles exist. Any
bot match you start (step 3 or the New match form) adds "Random Bot p1, p2, ..."
to it. `scripts/make_showcase.sh` records the GIFs and screenshots above.

All ports bind to `127.0.0.1` only. Stop with `docker compose down` (add
`--volumes` to also delete the database).

### Play a match

Every seat is a random bot for now, so a match costs nothing. In the terminal:

```bash
docker compose exec arena arena run --game toy --bots --seed 7
```

```
High Card (toy), players p1 p2, seed 7
   0  match_started    {"game": "toy", "version": "1", "players": ["p1", "p2"], "settings": {}, "seed": 7}  [spectators only]
   1  hand_dealt       {"player": "p1", "cards": [1, 3, 5]}  [only p1]
   ...
  18  match_finished   {"placements": [{"player": "p1", "rank": 2}, {"player": "p2", "rank": 1}]}
Result: 1. p2  2. p1
```

Liar's Deck and Poker work the same way (output shortened; the full logs are
120 and 641 lines). Hidden cards are marked `[only p1]` or `[spectators only]`,
as a spectator sees them:

```bash
docker compose exec arena arena run --game liars_deck --players 3 --bots --seed 7
```

```
Liar's Deck (liars_deck), players p1 p2 p3, seed 7
   0  match_started    {"game": "liars_deck", "version": "1", "players": ["p1", "p2", "p3"], "settings": {}, "seed": 7}  [spectators only]
   4  round_started    {"round": 1, "table_card": "queen", "starter": "p1", "hand_size": 5, "players": ["p1", "p2", "p3"]}
   8  action_accepted  {"player": "p1", "tool": "play_cards", "arguments": {"card_ids": ["Q6"]}}  [only p1]
   9  cards_played     {"player": "p1", "count": 1}
  ...
  24  trigger_pulled   {"player": "p3", "pull": 1, "live": true}
  ...
 116  match_over       {"winner": "p2"}
 117  match_finished   {"placements": [{"player": "p2", "rank": 1}, {"player": "p1", "rank": 2}, {"player": "p3", "rank": 3}]}
Result: 1. p2  2. p1  3. p3
```

```bash
docker compose exec arena arena run --game poker --players 3 --bots --seed 7
```

```
Poker (poker), players p1 p2 p3, seed 7
   0  match_started    {"game": "poker", "version": "1", "players": ["p1", "p2", "p3"], "settings": {}, "seed": 7}  [spectators only]
   1  hand_started     {"hand": 1, "button": "p1", "small_blind_player": "p2", "big_blind_player": "p3", "small_blind": 10, "big_blind": 20, "players": ["p1", "p2", "p3"]}
   ...
  10  bet_action       {"player": "p1", "kind": "raise", "street": "preflop", "to": 40, "added": 40}
   ...
 637  match_over       {"reason": "last_player", "winner": "p1"}
 638  match_finished   {"placements": [{"player": "p1", "rank": 1}, {"player": "p3", "rank": 2}, {"player": "p2", "rank": 3}]}
Result: 1. p1  2. p3  3. p2
```

Or through the API, with a second between turns so that it can be watched:

```bash
curl -X POST http://localhost:8100/matches -H "content-type: application/json" \
  -d '{"game": "toy", "turn_delay": 1}'
```

The answer holds the match `id`. `ws://localhost:8100/matches/<id>/events`
streams the events of the match from its first one while it is played;
`GET /matches/<id>/events` returns them as a list, `GET /matches` lists the
matches. Without Docker, `uv run arena run --game toy --bots` does the same as
the first command. `arena games` lists what can be played: `toy` is High Card,
the small reference game, `liars_deck` is Liar's Deck, `poker` is Poker and `werewolf` is Werewolf.

Configuration is optional. To change the database password or add a
model API key, copy `.env.example` to `.env` and edit it. `.env` is gitignored,
and Compose passes the key on to the arena. Only `arena run --models` uses
the key (see Cost safety).

## Real models: first matches

On 2026-11-11 the cheapest models of the roster played the first real matches,
started with `arena run --models`. The saved matches are in
[docs/examples](docs/examples/README.md), thoughts, bluffs and wolf chat
included.

| Game | Seats | Calls | Time | Cost |
| --- | --- | --- | --- | --- |
| Liar's Deck | 4 models | 33 | 2 min 41 s | 0.012 EUR |
| Poker, 20 hands | 6 models | 138 | 6 min 32 s | 0.054 EUR |
| Werewolf, 8 players | 8 models | 66 | 8 min 24 s | 0.041 EUR |

Six matches in all, tests included, cost 0.18 EUR. The very first one, the
same Liar's Deck table, took 21 minutes and 0.068 EUR, and 83 of its 130
answers were rejected: two models spent their whole answer thinking and never
made a move. What that changed in the agent runner is in
[docs/DECISIONS.md](docs/DECISIONS.md) ("One forced tool call carries the
thought and the move"). Models still make mistakes the server has to reject,
about one answer in five in the Werewolf match; a rejected answer gets a
second and third try, then a random legal move is played and the log says so.

## Cost safety

Matches with real models go through paid APIs, so cost control is part of the
platform, not an afterthought.

- **Hard caps:** €0.50 per match and €25 per calendar month by default, set in
  [config/models.yaml](config/models.yaml) next to the models and their
  prices.
- **Counted before it is spent:** every model call is written to a ledger in
  Postgres before it is sent, at the most it can cost, and corrected when the
  provider reports the real token counts. A call that fails or times out
  keeps its worst case. The ledger can therefore show more than the bill,
  never less, also after a crash or with several players calling at once.
- **Pause, not overrun:** a call that could take the match or the month past
  its cap is not sent. The engine pauses the match with the amounts in its log
  and can resume it later from the same turn, unchanged. Today nothing asks you
  to raise a cap or resume: a match started from the command line ends at a
  cap.
- **One door for real models:** `arena run --game <id> --models <id>,<id>,...`
  seats models from `config/models.yaml` and is the only thing here that
  spends money. It needs a database for the ledger and the key in the
  environment, and prints what each seat cost. Matches started through the
  API seat random bots. Development, tests and CI use random bots and a mock
  LLM only, and CI has no access to any API key.
- **Keys stay in `.env`:** never in code, config files, logs, the event log or
  the database. Provider error texts are dropped, because they can quote a
  key.

## Development

Python 3.12 and [uv](https://docs.astral.sh/uv/) are the only local
requirements besides Docker (Node 24 for the web UI).

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
arena/      core: API, engine, agent runner, cost caps, ratings, statistics, memory, chronicle, `arena` command
games/      one package per game: toy, liars_deck, poker, werewolf, civ (data, map, economy)
config/     cost caps, models and personalities (YAML)
mods/       extra content that overrides or extends game data
web/        spectator UI (SvelteKit)
scripts/    make_showcase.sh: records the README GIFs and screenshots
docs/       design spec, architecture, testing, decisions, credits
experiments/ one plan per experiment, written before its first paid match
research/   research plan and reports
tests/      tests for the arena core
```

## Documentation

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): the building blocks and one turn, with diagrams.
- [docs/TESTING.md](docs/TESTING.md): tests, lint, secret scan and the compose smoke test.
- [docs/DESIGN.md](docs/DESIGN.md): the full design spec (German).
- [docs/DECISIONS.md](docs/DECISIONS.md): decisions taken where the spec is open or overridden.
- [docs/CREDITS.md](docs/CREDITS.md): origin of every asset.
- [research/README.md](research/README.md): how the models are evaluated; plans in [experiments/](experiments/README.md).
- [CLAUDE.md](CLAUDE.md): architecture and conventions for contributors, human or AI.
