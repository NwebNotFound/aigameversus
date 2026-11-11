# Credits

Every asset in this repository (art, icons, fonts, sounds) is listed here with
its origin, and so is every library and image the project builds on. Only
hand-made or generated assets are allowed; nothing is copied from existing
games. The game *Liar's Deck* is an original game: its name, rules text and art
are not taken from any other game.

## Art and images

All art is original. It is drawn in code (inline SVG and CSS) or produced by a
script from the running UI; no image file was downloaded or copied.

| Asset | Path | What it is for | How it was made |
| --- | --- | --- | --- |
| Logo and favicon (two chevrons) | `web/src/lib/assets/favicon.svg` | tab icon, nav logo | original, hand-written SVG |
| Liar's Deck table: avatars, card faces and backs, revolver cylinder | `web/src/lib/components/LiarsDeckTable.svelte` | the live view and replays of Liar's Deck | original, inline SVG and CSS |
| Poker table: avatars, card faces and backs, chip stacks, dealer button | `web/src/lib/components/PokerTable.svelte` | the live view and replays of Poker | original, inline SVG and CSS |
| Werewolf circle: avatars, night and day backdrop, moon and sun, vote arrows | `web/src/lib/components/WerewolfCircle.svelte` | the live view and replays of Werewolf | original, inline SVG and CSS |
| Player avatars (a letter in a coloured ring) | the three components above | seats of every table | original, inline SVG |
| Screenshots | `docs/images/*.png` | README and docs | taken from this UI with Playwright; every player is a random bot |
| UI screenshots (before and after) | `docs/images/ui/*.png` | `docs/UI-DESIGN.md`, UI pull requests | taken from this UI with Playwright; the players are random bots or the models of `docs/examples/` |
| Player avatars on the watch screen (a lit disc with an initial and a small mark, coloured by model) | `web/src/lib/components/Avatar.svelte` | the cast, the commentary | original, inline SVG |
| Result card (podium, team banner) | `web/src/lib/components/ResultCard.svelte` | the end of a match on the watch screen | original, CSS |
| Stage beats (call-out, light rings, night tint) and the revolver hammer | `web/src/lib/components/Beats.svelte`, `LiarsDeckTable.svelte` | the watch screen | original, CSS and inline SVG |
| View switch and thought icons (eye, crossed eye, lock) | `web/src/lib/components/ViewSwitch.svelte`, `Commentary.svelte` | the watch screen | original, inline SVG |
| GIFs | `docs/images/showcase-*.gif` | README | recorded from this UI by `scripts/make_showcase.sh` (Playwright frames, assembled with Pillow); random bots only |

Fonts: none are bundled; the UI uses the system font stack (see `web/src/app.css`).
Sounds: none.

## Libraries

Used as dependencies, not copied into the repository. Versions are in
`uv.lock` and `web/package-lock.json`.

| Library | Role | Licence |
| --- | --- | --- |
| FastAPI, uvicorn, websockets | the arena API and the WebSocket stream | MIT, BSD-3-Clause, BSD-3-Clause |
| Pydantic | data models and validation | MIT |
| asyncpg | PostgreSQL access | Apache-2.0 |
| redis-py | Redis client (the worker's queue and heartbeat) | MIT |
| jsonschema, PyYAML | validation and loading of the game data files | MIT |
| LiteLLM | the only door to real models (behind the cost caps) | MIT |
| pytest, ruff, httpx2 | tests, lint and format, the test HTTP client | MIT, MIT, BSD-3-Clause |
| SvelteKit, Svelte, Vite | the spectator UI | MIT |
| Playwright | browser tests and the README recordings | Apache-2.0 |
| Vitest, Prettier, svelte-check, TypeScript | web tests and checks | MIT, MIT, MIT, Apache-2.0 |
| Pillow | assembles the README GIFs (fetched on demand, not a dependency) | MIT-CMU (HPND) |

## Images and tools in the stack

PostgreSQL 18 and Redis 8 (the official images), Node 24 and Python 3.12 (base
images), [uv](https://docs.astral.sh/uv/), and gitleaks in CI. Each keeps its own
licence; none is modified.

## Models

Real models are reached only through OpenRouter, only from the `arena` command,
and only inside the cost caps. The only model output in the repository is
`docs/examples/*.json`: unedited logs of three matches played through
OpenRouter inside the cost caps (which models: see `docs/examples/README.md`).
Everything else, including every screenshot and GIF, comes from random bots.
