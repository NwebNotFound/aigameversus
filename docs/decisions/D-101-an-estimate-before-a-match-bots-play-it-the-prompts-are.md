# D-101 · An estimate before a match: bots play it, the prompts are measured

- **Date:** 2026-11-11
- **Decision:** `POST /matches/estimate` takes a game, models and settings
  and answers what the match would cost per seat and in total, the month so
  far, the caps, and whether it fits. Random bots play the match with seeds 1
  to 3; every prompt each seat's model would get is built by the runner's own
  code (rules and summary of the prompt version included) and measured. A
  seat costs its most expensive trial: prompt bytes / 3.5 as input tokens,
  one answer per prompt at the model's mean output tokens in the ledger, or
  at the output limit while the ledger has fewer than 10 of its answers,
  all times 1.3 for corrections and retries, priced like the budget prices a
  call; each seat says its `basis` (`ledger history` or `output limit`, which
  is several times too high). It calls no model and needs no flag; 503 while
  the ledger is down. One estimate runs at a time and the same request gets
  the same answer for 30 seconds, because the trial matches take the
  server's CPU and the API has no login.
- **Why:** Before a paid run the person starting it should see the price,
  and the launch form needs a number to show. Measuring real prompts follows
  every game, player count and prompt version without a table to maintain.
  The output of an answer differs twentyfold between models (67 to 1101
  tokens per answer in the first 390 calls), so the ledger's history is the
  best guide, and the limit is the safe one without it.
- **Alternatives:** A fixed price per game (wrong for every other player
  count, setting or model); the budget's own upper bound (bytes as tokens and
  the full output limit: ten times too high to be useful); an estimate from
  past matches only (none for a new game or model).
