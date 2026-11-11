# D-090 · Experiments are registered as files before their first paid match

- **Date:** 2026-11-11
- **Decision:**
  - An experiment is one YAML file in `experiments/` with its question, fixed
    conditions, models (ids and prices of that day), stages, hypotheses with
    their tests, stopping and exclusion rules and budgets. Every paid run
    needs the project owner's own yes: the plan lists it per stage under
    `approvals`. An approved stage changes only by a dated entry under
    `amendments`.
  - The schedule (every match: seed, seating, order) is generated from the
    plan by `arena/research/experiment.py` and stored next to it; a test keeps
    the two in step.
  - Tables have four seats and are balanced by design, not by chance: eight
    models at 14 tables where every pair meets 3 times; each seed played with
    4 seatings that give every model every seat once; one model at two
    reasoning efforts in all 6 arrangements; one guest in every seat among
    three hosts.
  - One seed is played with all seatings of its table. The luck of a seed
    (cards, revolver) belongs to the seat, so every model at the table gets
    the same luck once.
  - A plan's budgets, the money spent before and a reserve must fit under the
    monthly cap, or the plan does not load. Experiment 1 keeps 20 % of the
    cap unplanned.
- **Why:** Hypotheses and tests fixed before the data cannot be bent to fit
  it. Balanced seatings take seat and card luck out of the comparison with far
  fewer matches than random seating needs, and matches cost money.
- **Alternatives:** random seatings and seeds (more matches for the same
  precision); a full round robin of all 70 tables of four (5 times the cost);
  plans as prose only (nothing to check a schedule against).
