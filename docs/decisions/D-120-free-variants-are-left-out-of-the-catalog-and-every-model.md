# D-120 · Free variants are left out of the catalog, and every model says how reliably it has played here

- **Date:** 2026-11-12
- **Decision:** `GET /models/catalog` leaves out the `:free` variants unless
  `free=1`, and marks them `rate_limited_likely`; the paid twin of the same
  model stays. Every model in the catalog and on its model page carries
  `reliability` from the arena's own logs (`arena/db/reliability.py`):
  `unreliable` when its seat gave up in one of its last 2 matches, or the
  random bot played more than half of its last 20 moves; `unknown` below 20
  moves; else `ok`; with the reason, the number of moves, and warnings that
  are not failures (answers cut off at the output limit, often rate-limited).
  An unreliable model stays selectable. The tool rule (`tools` and
  `tool_choice`) is unchanged; verdicts are reused for 60 seconds. The
  thresholds are `reliability` in `config/models.yaml`. A model in two seats
  of one match counts that match once. Cut-off and rate-limit figures rest
  only on moves that report them (logs before the counters say nothing, they
  are not zeros), and the answer says how many moves did (`telemetry_moves`).
- **Why:** The owner's run seated a free Gemma variant whose route refused
  every call, so the random bot played all its moves. Its tools were fine; its
  route was not. A verdict from what happened here tells that apart from a
  model that cannot play, and hiding by default keeps the form clean without
  forbidding anything.
- **Alternatives:** Removing free variants (they work when the route is idle);
  judging by the provider's declarations (they certify nothing); one error
  rate (a cut-off answer and a throttled route are not the model's fault).
