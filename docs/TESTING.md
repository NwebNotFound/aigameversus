# Testing

Same checks as CI (`.github/workflows/ci.yml`). Tests use random bots and the
mock LLM only; nothing calls a paid model.

## Setup

```bash
uv sync --frozen           # install into .venv from uv.lock
docker compose up -d --wait db   # Postgres on 127.0.0.1:5433 for the database tests
```

Without a reachable Postgres, the tests under `tests/db/` are skipped locally.
With `CI` set they fail instead. Use another server with
`ARENA_TEST_DATABASE_URL`. Each database test runs in its own schema.

## Commands

```bash
uv run pytest                          # everything (tests/ and games/)
uv run pytest games/werewolf           # one game folder
uv run pytest tests/engine -k replay   # one area, filtered by name
uv run ruff check .                    # lint
uv run ruff format --check .           # formatting (use `ruff format .` to fix)
```

Arena core tests live in `tests/`, a game's tests in `games/<id>/tests/`.

## Secret scan

CI scans the full git history with gitleaks:

```bash
MSYS_NO_PATHCONV=1 docker run --rm --volume "$(pwd -W):/repo" \
  ghcr.io/gitleaks/gitleaks:v8.30.1 git /repo --redact --no-banner
```

On Linux or macOS use `--volume "$PWD:/repo"` and drop `MSYS_NO_PATHCONV`.

## Compose smoke test

```bash
docker compose up --build --detach --wait --wait-timeout 180
curl --fail http://127.0.0.1:8100/health
curl --fail --output /dev/null http://127.0.0.1:3100/   # the SvelteKit web UI
docker compose logs      # on failure
docker compose down      # add --volumes to also delete the database
```

Stop only this project (`aigameversus`); other stacks may run on the same
machine.

## Web UI

The spectator UI in `web/` is a SvelteKit app (TypeScript). Run these in `web/`:

```bash
npm ci                 # install from package-lock.json
npm run lint           # Prettier check + svelte-check
npm run test:unit      # Vitest
npm run build          # production build
```

The Playwright smoke tests open the running UI on port 3100, so start the stack
first and then run them:

```bash
docker compose up --build --detach --wait --wait-timeout 180   # from the repo root
cd web && npx playwright test
```

- `WEB_URL` overrides the address, for example `WEB_URL=http://127.0.0.1:5173`
  against `npm run dev`.
- Two projects run every test: `mobile-375` and `desktop-1280` (viewport widths).
- Traces are written to `web/test-results`; CI uploads them when a test fails.
  Open one with `npx playwright show-trace <trace.zip>`.

## Windows notes

- Use Git Bash, not PowerShell or cmd.
- `export PYTHONIOENCODING=utf-8` before running Python.
- Git Bash rewrites paths in `docker run` mounts: use `MSYS_NO_PATHCONV=1` and
  `"$(pwd -W)"`.
- Host ports: API 8100, web 3100, Postgres 5433, Redis 6380.
