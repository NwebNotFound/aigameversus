# D-030 · Spectator UI: SvelteKit 3 on Node, API calls server-side, English chrome

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
