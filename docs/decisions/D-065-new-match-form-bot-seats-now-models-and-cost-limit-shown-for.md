# D-065 · New-match form: bot seats now, models and cost limit shown for later

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
