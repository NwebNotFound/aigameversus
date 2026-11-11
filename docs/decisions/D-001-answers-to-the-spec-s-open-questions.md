# D-001 · Answers to the spec's open questions

- **Date:** 2026-11-11
- **Decision:** Frontend is SvelteKit. The in-game language is a per-match
  setting, default German. The default budget is €0.50 per match with a hard
  cap of €5 per month; at a cap the match pauses and asks. The default roster
  is a set of cheap OpenRouter models, listed in `config/models.yaml` when
  model calls land (step 1.5).
- **Why:** Set by the project owner before the build started.
- **Alternatives:** React; a fixed language; per-day instead of per-month cap.
