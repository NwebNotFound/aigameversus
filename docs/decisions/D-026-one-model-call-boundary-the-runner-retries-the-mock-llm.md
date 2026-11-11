# D-026 · One model-call boundary; the runner retries; the mock LLM stands behind it

- **Date:** 2026-11-11
- **Decision:** The agent runner (`ModelAgent`) reaches its model only through
  a `ModelCall`: messages and tool schemas in, text and raw tool calls out,
  `ModelError(reason, retryable)` on failure. `MockLLM` and `LiteLLMModel`
  implement it. The runner retries a failed call 3 times with pauses of 1, 2
  and 4 seconds; a failure marked as not retryable (wrong key, bad request) is
  not retried. When that is used up, the model counts as failed for good: the
  runner raises `AgentError` and the engine takes the seat (D-025). LiteLLM's
  own retries are switched off. `LiteLLMModel` imports LiteLLM on first use
  and in LiteLLM's offline mode; it maps a failure to its class name and drops
  the provider's message.
- **Why:** With the mock at the boundary, prompt building, answer parsing,
  retries and the engine run for real in tests, at no cost. One retry policy
  in one place can be tested with a fake sleep. Seven seconds of patience
  cover a rate limit or a dropped connection; a longer outage would stall
  every turn of that seat, so the seat is handed over once instead. Importing
  LiteLLM takes seconds and downloads a price list unless offline mode is set,
  which no test, CLI start or bot match should pay for. Provider messages can
  quote the request or part of a key, so only the kind of failure travels on.
- **Alternatives:** Mocking the HTTP layer (tests would depend on one
  provider's wire format); LiteLLM's built-in retries (not visible to the
  match, not testable without the network); losing the seat only after
  several failed turns in a row (more state for a rare case; can be added if
  real matches show short outages).
