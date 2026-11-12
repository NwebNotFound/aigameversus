# D-146 · Insights across matches: whole-match resampling, one head-to-head result per match

- **Date:** 2026-11-12
- **Decision:** `GET /insights?game=&demo=` (`arena/api/insights.py`, the numbers in
  `arena/ratings/insights.py`) reports per model, over its rated matches:
  - matches and wins;
  - a win rate and a placement score (1 for first, 0 for last), each with a 95 % interval
    from 2000 resamples of whole matches, seeded;
  - the cost per match from the ledger;
  - the reliability verdict of `arena/db/reliability.py`;
  - for every pair of models that met, a head-to-head with one result per match and a Wilson
    interval.

  Below 10 matches a number is provisional. docs/METRICS.md "Across matches" defines each
  number.
- **Why:**
  - Lead's task (the design review, step 10: views 7, 8 and 10 of the Insights page).
    docs/METRICS.md requires resampling whole matches: the seats of one match are not
    independent.
  - One value per model and match is how a model with two seats of one table (the W2
    duplicate-model tables) is counted once.
  - Seeded resampling makes the answer a function of the data, testable and cacheable.
  - The placement score lets 2-player and 8-player tables share one scale.
- **Alternatives:**
  - A Wilson interval on the win rate. It treats seats as independent, wrong for duplicate
    seats, and gives nothing for placement.
  - A rating interval from re-running Elo on resamples. It is order-dependent and touches the
    Elo core (Arena Builder's). It is left for later, as `rating_low` / `rating_high`.
  - Head-to-head per pair of seats: two seats of A against one of B would count twice per
    match.
  - The behaviour views 1, 2 and 4 (lies, calls, treaties) need every match's analytics.
    They follow in their own PR.
