# D-034 · Money is counted per model call, in a ledger, before the call is sent

- **Date:** 2026-11-11
- **Decision:** Every model call of a match goes through `Budget.meter`
  (`arena/agents/budget.py`). Before the call is sent it is booked in the
  `model_calls` table at the most it can cost: the size of the request in
  bytes as its input tokens, the output limit as its output tokens. If that
  booking would take the match or the calendar month (UTC) past its cap, the
  call is not sent. When the provider reports the tokens, the booking is
  corrected to the real cost. A call that reports nothing (an error, a
  timeout, an answer without usage, a crash) keeps its upper bound. Should a
  provider report more than the bound, the real cost is booked all the same:
  the cap is then passed by that difference, and the next call pauses. Check and
  booking are one transaction under an advisory lock. Money is an integer of
  millionths of a euro, rounded up per call. A prompt whose upper bound is
  above `max_input_tokens` is not sent; that seat goes to the random bot.
  `Budget.model` is the only place that builds a real model, already metered.
- **Why:** "Hard cap" has to hold in the cases where counting afterwards
  fails: several players calling at once, a turn that times out while the
  provider still answers and bills, a process that dies between call and
  bookkeeping, two processes running matches. Booking the worst case first
  covers all of them with one rule, and every error is on the safe side: the
  ledger can show more than was billed, never less. No tokenizer produces
  more tokens than its text has bytes, so the bound needs no tokenizer and
  holds for every model, as long as the provider keeps to the output limit it
  was sent. If one does not, a ledger that tells the truth is worth more than
  a cap that looks kept. Integers keep sums exact and identical in any order.
  The input limit also keeps prompts below the sizes at which some providers
  charge a higher price per token.
- **Alternatives:** Adding up the cost after each call (a cap can be passed
  by as many calls as are in flight, and a cancelled call is never counted);
  charging nothing for failed calls (wrong when the provider billed a call
  that timed out on our side); LiteLLM's built-in cost tracking (prices come
  from a list bundled with the library, in memory only); the cost a provider
  reports per call (provider-specific; can replace the price list later);
  cost events in the match log (a dropped turn would lose them, D-035).
