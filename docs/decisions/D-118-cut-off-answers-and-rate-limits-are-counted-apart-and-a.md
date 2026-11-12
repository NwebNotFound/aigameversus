# D-118 · Cut-off answers and rate limits are counted apart, and a model is qualified per route, game and configuration

- **Date:** 2026-11-12
- **Decision:** Every model move's `decision` event also counts `cutoffs`
  (answers that ran into the output limit) and `rate_limits` (calls refused
  as too many requests), apart from other retries and refusals. The Liar's
  Deck analytics read the move figures from the `decision` event (they read
  them from `action_accepted`, where they never were) and add both counts
  per player; the behaviour report names `cut_off` and `throttled` as
  reliability reasons of their own. Whether a model is qualified is decided
  by the Researcher's protocol (research/QUALIFY.md) for one exact
  combination of provider id, route, game, prompt and runtime settings; the
  arena's figures map onto its reasons as in
  [model-qualification.md](../model-qualification.md).
- **Why:** In match be2f808a twelve of thirteen refused answers were cut off
  at 1500 tokens and one seat failed on a free route's rate limit; a filter
  that only counts bot moves showed neither, and calling either "no tool
  support" would judge the configuration or the route, not the model.
- **Alternatives:** One error rate per model (mixes route, limit and skill);
  qualifying by model name (a different route or limit behaves differently);
  reading the provider's declared parameters as proof (they certify nothing).
