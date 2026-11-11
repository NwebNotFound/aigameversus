## What and why

<!-- One or two sentences. Link the roadmap step or the issue. -->

## Checked

- [ ] `uv run pytest` and `uv run ruff check . && uv run ruff format --check .` (and in `web/`: `npm run lint`, `npm run test:unit`, `npx playwright test` when the UI changed)
- [ ] No secret, no personal data, no copied asset (new art is listed in `docs/CREDITS.md`)
- [ ] A new decision is its own file in `docs/decisions/` (`python scripts/decisions.py new D-0NN "Title"`) with a claimed `D-` number
- [ ] README, `CLAUDE.md` and docs updated where the change makes them wrong
