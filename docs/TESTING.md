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

### Sharing the stack on one machine

Several agents work on this project on the same machine, and they share one
Compose project (`aigameversus`) and its fixed ports. Before any
`docker compose up`, `down` or `build`:

1. Create the lock file `AIGameVersus/.compose.lock` in the team's shared
   folder, containing your name and the time.
2. If it already exists and is younger than 30 minutes, do not touch the
   stack; try again in 2 minutes. An older lock is stale and may be taken.
3. Delete the lock when you are done, also after a failed run.

Tests that need only Postgres or Redis use the stack under the same lock. Pure
unit tests need no lock. Working alone on your own machine, skip this.

## Commands

```bash
uv run pytest                          # everything (tests/ and games/)
uv run pytest games/werewolf           # one game folder
uv run pytest tests/engine -k replay   # one area, filtered by name
uv run ruff check .                    # lint
uv run ruff format --check .           # formatting (use `ruff format .` to fix)
```

Arena core tests live in `tests/`, a game's tests in `games/<id>/tests/`.

## Model players in tests

A test never calls a model. It gives `ModelAgent` a `MockLLM` with a script:
answers, functions that answer from the prompt, `ModelError`s to raise, or
`HANGS` for a model that never answers.

```python
mock = MockLLM(ModelError("RateLimitError"), tool_call("play_card", {"card": 3}))
agent = ModelAgent(mock, plugin, sleep=no_pause)   # no real waiting between retries
match = Match(plugin, {"p1": agent, ...}, seed=1, turn_timeout=0.2)
```

`mock.calls` holds every prompt the model would have seen. Patterns for whole
matches, timeouts and API errors are in `tests/agents/test_model_match.py`.

## Matches over the API and the command line

`tests/db/test_matches_api.py` starts matches through FastAPI's `TestClient`
and follows them over WebSocket; the server closes the stream when the match
stops:

```python
match = client.post("/matches", json={"game": "toy", "seed": 5}).json()
with client.websocket_connect(f"/matches/{match['id']}/events") as stream:
    first = stream.receive_json()  # {"seq": 0, "type": "match_started", ...}
```

`tests/db/test_server.py` does the same once through a real uvicorn server on
a free port and a real WebSocket client, because the test client never opens a
socket and would not notice a server that cannot speak WebSocket.

`turn_delay` in the request keeps a match running long enough to look at it
while it plays. The `fake_games` fixture (`tests/conftest.py`) replaces the
`games` folder by plugins a test writes itself, for example a broken one.
`tests/test_cli.py` calls `arena.cli.main([...])` and reads what it printed.
`tests/test_games.py` plays and replays a bot match of every game it finds,
so a new game is covered as soon as its folder exists.

## Cost caps in tests

The caps are tested against the real ledger table, so these tests are database
tests (`tests/db/test_budget.py`). A mock model reports its tokens with
`tool_call(..., usage=Usage(1000, 100))`; without `usage` a call keeps its
upper bound. The test config has a model that costs one and two millionths of
a euro per token, and the clock is a parameter:

```python
budget = Budget(Ledger(pool), match_id, config(), now=lambda: NOVEMBER)
agent = ModelAgent(budget.meter("p1", "cheap", mock), plugin, sleep=no_pause)
budget.match_cap = 6000  # millionths of a euro
with pytest.raises(MatchPaused):
    await match.run()
budget.match_cap = 1_000_000  # the user allows more
await match.run()  # continues with the dropped turn
```

The engine side of a pause needs no database: `tests/engine/test_pause.py`
uses agents that raise `MatchPaused` themselves.

Two test modules load LiteLLM (about 4 seconds): `tests/agents/test_litellm_model.py`
and `tests/db/test_budget.py`. They use the `litellm` and `answer_with`
fixtures from `tests/conftest.py`, which answer with LiteLLM's own mock
responses and refuse every name lookup, so a test fails if anything tries to
reach the network.

## Secret scan

CI scans the full git history with gitleaks:

```bash
MSYS_NO_PATHCONV=1 docker run --rm --volume "$(pwd -W):/repo" \
  ghcr.io/gitleaks/gitleaks:v8.30.1 git /repo --redact --no-banner
```

On Linux or macOS use `--volume "$PWD:/repo"` and drop `MSYS_NO_PATHCONV`.

## Sharing the stack with other agents

Several agents share this machine, one Compose project and its fixed ports.
Before `docker compose up`, `down` or `build` on the `aigameversus` stack (also
for tests that need only Postgres or Redis), take the lock: create
`C:\Users\nilsw\OpenBot\Shared\AIGameVersus\.compose.lock` with your name and
the time. If it exists and is younger than 30 minutes, wait and retry in
2 minutes; an older lock is stale and may be taken. Delete it when you are done.
Pure unit tests need no lock.

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

The Playwright smoke tests open the running UI on port 3100. Start the stack,
fill it with demo ratings for the leaderboard tests, then run them:

```bash
docker compose up --build --detach --wait --wait-timeout 180   # from the repo root
docker compose exec -T arena python -m arena.ratings.demo_seed --matches 30
cd web && npx playwright test
```

`demo_seed` creates six "DEMO …" profiles and rates random-bot High Card
matches between them: no model is called. The same seed gives the same matches,
and running it again adds nothing. It refuses to run when the database holds any
profile that is not a demo profile, so it never mixes with real results.

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
