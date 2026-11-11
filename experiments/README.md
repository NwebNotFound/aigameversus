# Experiments

One YAML file per experiment, written **before** its first paid match: the
question, the fixed conditions, the models with their ids and prices on that
day, the stages, the hypotheses with their tests, the rules for stopping and
excluding, and the budget. Next to it lies `<name>_schedule.csv`: every match
the plan fixes, with seed, seating and order.

| File | Question | Status |
| --- | --- | --- |
| [E1_liars_deck.yaml](E1_liars_deck.yaml) | Liar's Deck: do cheap models differ, does more reasoning help, do stronger models win? | approved (B and C after A); nothing played |

## Rules

- Every paid run needs the project owner's own yes. A plan lists what he has
  agreed to under `approvals`, stage by stage; a stage without an entry
  spends nothing, and an approved stage spends at most its budget.
- After approval a plan changes only by an entry under `amendments` (date,
  what, why) and a higher `version`. Results never change a hypothesis, a test
  or a stopping rule.
- Every registered test is reported, whatever it finds.
- No file here holds a key, a name of a person or anything else private.

## Check a plan and write its schedule

```bash
uv run python -m arena.research.experiment experiments/E1_liars_deck.yaml > experiments/E1_liars_deck_schedule.csv
uv run pytest tests/research
```

Loading refuses a plan with an unknown field, a stage that names a model the
plan does not list, or budgets that add up to more than the monthly cap. The
tests compare each stored schedule with the one its plan gives and count the
balance of every stage (matches per model, per seat, per seed).

## How a schedule is built

`arena/research/design.py` has the seatings, each for a table of four:

- **league:** eight models at 14 tables, every pair of models together at 3 of
  them. Each table plays each of its seeds with 4 seatings, so every model
  gets every seat, and with it the cards and the revolver of that seat, once.
- **mirror:** one model in all four seats, two seats at each of two reasoning
  efforts, in all 6 arrangements.
- **guests:** one guest in each seat among three hosts that keep their order,
  12 seatings.

A seat in the schedule reads `model@effort`. Pilot matches come first; then a
stage plays one replicate (one seed per table) after the other, in an order
shuffled from the stage's `seed_base`.
