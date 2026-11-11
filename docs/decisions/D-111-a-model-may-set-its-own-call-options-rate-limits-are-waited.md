# D-111 · A model may set its own call options; rate limits are waited out longer, within a budget

- **Date:** 2026-11-11
- **Decision:** A model in `config/models.yaml` may set `max_output_tokens`,
  `reasoning_effort` (one of the efforts, or `off`: the option is not sent)
  and `tool_choice` (`required`, the default, or `auto`); what it does not
  set comes from `limits` (`call_options` in `arena/config.py`). The budget
  books a call at that model's own output limit, so a longer limit never
  passes a cap unnoticed. qwen-flash gets 4000 output tokens, no reasoning
  effort and `auto`. A rate limit (`RateLimitError`) is waited out 3, 6 and
  12 seconds instead of 1, 2 and 4, every pause is up to half longer at
  random, and one seat may wait out 12 rate limits in a match; after that a
  rate limit costs it its seat like any other failure. A call refused with a
  rate limit is booked at 0: a 429 is refused before anything is generated,
  like the refused requests of D-071; every other failed call keeps its upper
  bound, because the provider may have billed it.
- **Why:** In the first matches qwen-flash thought through its whole output
  limit and then called no tool, and OpenRouter takes no reasoning effort for
  it; gemini-flash-lite was throttled, and four seats retrying in step after
  1 s hit the limit again. A budget keeps a throttled model from stretching
  every turn to its time limit for a whole match. In the real ledger, 48
  unsettled calls (5 % of what was booked, over a third of qwen-flash's) were
  rate limits and refusals that cost nothing but stood at the full bound.
- **Alternatives:** Raising the limits for every model (books every call
  higher and lets other models think longer for nothing); options from
  OpenRouter's metadata (a second source of behaviour; the runner already
  retries a refused request without the options); waiting for a rate limit
  without a budget (a match of hours).
