# Throne of Tokens: balance sweep with random bots

2026-11-12, on main b154499. Bots only: no model, no cost. Reproduce with

```bash
uv run python -m arena.research.civ_balance --seeds 20 --markdown
```

(`arena/research/civ_balance.py`; every number is read from the event logs.)

**What it can and cannot say.** The random bot (`games/civ/bot.py`) builds,
trains, settles, moves and answers offers at random. It never declares war and
never attacks a nation. Only the barbarians fight. So the sweep measures the
economy, settling, the barbarians and the win rules, not wars between nations,
diplomacy or strategy. Use it to find rules that break without any strategy.
Model matches still have to show how they play.

## Summary

- **No seat is favoured.** In the first 20 seeds p1 ranked below average in
  every table, but with 80 seeds that is gone: four nations over 20 rounds
  2.39 / 2.59 / 2.41 / 2.52 (p1-p4), and over 60 rounds 2.38 / 2.60 / 2.42 /
  2.49. Order resolution in seat order gives no measurable edge.
- **Start regions are not equal (proposal D-138).** Nations whose start region
  is short of food or gold rank 0.4 to 1.0 places worse than those short of
  iron or wood, in every table and with 80 seeds (four nations, 60 rounds:
  food 2.69, gold 2.71, iron 2.27, wood 2.21). Food- and gold-short regions
  have the fewest food or gold tiles, and both resources count in the score.
- **Early domination by settling (proposal D-137).** With four nations,
  10 of 80 matches of 60 rounds end by domination, 9 of them by round 26, the
  earliest in round 7: whoever settles twice first holds half of very few
  cities. Five and six nations never dominate. Requiring two cities per
  nation in the world first removes the wins before round 18 (in memory, same
  seeds).
- **The economic victory is rare.** 500 gold held for 5 rounds: 4 wins in 120
  matches, all with 5 or 6 nations over 60 rounds; the countdown started in
  7 of 60 full matches, and never in 20 rounds. With bots this is expected
  (they spend at random). For the 20-round C1 pilot it means the economic
  path is out of reach unless a model saves from the start.
- **Most matches go to the round limit.** 110 of 120. The median score gap
  between first and second is 17 to 36 points in 60 rounds and 7 to 13 in 20.
  That is no runaway: places stay contested.
- **Dropped orders are low.** 0.9 % to 2.7 % of the bots' orders, mostly moves
  onto a tile another nation holds (refused without a war). Models will
  differ. This is the floor for orders built from \`legal\`.
- **Barbarians matter a little.** About one neutral city and one barbarian
  conquest per match. A nation is knocked out in 0.15 to 0.35 matches on
  average, after barbarians took its cities or a rebellion made them neutral
  (bots never attack each other).

## The sweep (20 seeds per table)

| table | matches | round limit / domination / economy | mean rounds | dropped orders | countdown reached (best) | eliminated | neutral cities | barbarian conquests | median score gap 1st-2nd |
|---|---|---|---|---|---|---|---|---|---|
| 4x60 | 20 | 16 / 4 / 0 | 52.8 | 1.7% | 1 (2) | 0.25 | 0.95 | 0.95 | 35.5 |
| 5x60 | 20 | 19 / 0 / 1 | 59.1 | 1.9% | 2 (5) | 0.35 | 1.05 | 1.05 | 17.0 |
| 6x60 | 20 | 17 / 0 / 3 | 58 | 2.7% | 4 (5) | 0.25 | 1.25 | 1.25 | 20.5 |
| 4x20 | 20 | 18 / 2 / 0 | 19.4 | 0.9% | 0 (0) | 0.15 | 0.65 | 0.65 | 13.0 |
| 5x20 | 20 | 20 / 0 / 0 | 20 | 1.1% | 0 (0) | 0.2 | 0.65 | 0.65 | 8.5 |
| 6x20 | 20 | 20 / 0 / 0 | 20 | 1.4% | 0 (0) | 0.2 | 0.7 | 0.7 | 7.0 |

| table | seat | mean rank | wins | mean cities |
|---|---|---|---|---|
| 4x60 | p1 | 3 | 4 | 1.9 |
| 4x60 | p2 | 2.35 | 6 | 2.5 |
| 4x60 | p3 | 2.25 | 4 | 2.15 |
| 4x60 | p4 | 2.35 | 6 | 2.25 |
| 5x60 | p1 | 3.5 | 1 | 1.9 |
| 5x60 | p2 | 2.75 | 5 | 2.25 |
| 5x60 | p3 | 2.9 | 3 | 2.15 |
| 5x60 | p4 | 3 | 4 | 2.25 |
| 5x60 | p5 | 2.6 | 8 | 2.2 |
| 6x60 | p1 | 3.85 | 5 | 2.05 |
| 6x60 | p2 | 3.6 | 5 | 2.2 |
| 6x60 | p3 | 3.65 | 1 | 2.15 |
| 6x60 | p4 | 3.35 | 4 | 2.15 |
| 6x60 | p5 | 3.3 | 3 | 2.35 |
| 6x60 | p6 | 3.15 | 2 | 2.3 |
| 4x20 | p1 | 2.8 | 4 | 1.65 |
| 4x20 | p2 | 2.65 | 5 | 1.85 |
| 4x20 | p3 | 2.05 | 6 | 2 |
| 4x20 | p4 | 2.3 | 6 | 1.95 |
| 5x20 | p1 | 3.3 | 2 | 1.5 |
| 5x20 | p2 | 2.5 | 7 | 2 |
| 5x20 | p3 | 3.15 | 2 | 1.75 |
| 5x20 | p4 | 2.75 | 7 | 2 |
| 5x20 | p5 | 3.05 | 3 | 1.85 |
| 6x20 | p1 | 3.75 | 3 | 1.8 |
| 6x20 | p2 | 3.5 | 4 | 1.8 |
| 6x20 | p3 | 3.7 | 3 | 1.9 |
| 6x20 | p4 | 3.15 | 4 | 1.9 |
| 6x20 | p5 | 3.4 | 4 | 2 |
| 6x20 | p6 | 3.15 | 2 | 1.8 |

| table | start region short of | mean rank |
|---|---|---|
| 4x60 | food | 3 |
| 4x60 | gold | 2.55 |
| 4x60 | iron | 2.15 |
| 4x60 | wood | 2.25 |
| 5x60 | food | 3.56 |
| 5x60 | gold | 3.46 |
| 5x60 | iron | 2.42 |
| 5x60 | wood | 2.3 |
| 6x60 | food | 3.78 |
| 6x60 | gold | 4.1 |
| 6x60 | iron | 3.52 |
| 6x60 | wood | 2.64 |
| 4x20 | food | 2.9 |
| 4x20 | gold | 2.9 |
| 4x20 | iron | 1.9 |
| 4x20 | wood | 2.1 |
| 5x20 | food | 3.44 |
| 5x20 | gold | 3.54 |
| 5x20 | iron | 2.38 |
| 5x20 | wood | 2.39 |
| 6x20 | food | 3.78 |
| 6x20 | gold | 3.74 |
| 6x20 | iron | 3.28 |
| 6x20 | wood | 3.03 |

## Checks beyond 20 seeds

Seat ranks, 80 seeds per table, 20 rounds (p1, p2, ...):

| nations | mean rank by seat | wins by seat |
|---|---|---|
| 4 | 2.39, 2.59, 2.41, 2.52 | 22, 19, 23, 17 |
| 5 | 2.84, 2.86, 2.94, 3.10, 3.00 | 18, 19, 16, 12, 17 |
| 6 | 3.40, 3.23, 3.90, 3.45, 3.39, 3.35 | 17, 19, 11, 11, 11, 12 |

Rank by the resource a start region is short of, 80 seeds:

| table | food | gold | iron | wood |
|---|---|---|---|---|
| 4 nations, 20 rounds | 2.64 | 2.85 | 2.20 | 2.23 |
| 5 nations, 20 rounds | 3.30 | 3.20 | 2.71 | 2.60 |
| 6 nations, 20 rounds | 3.92 | 3.90 | 2.95 | 3.16 |
| 4 nations, 60 rounds | 2.69 | 2.71 | 2.27 | 2.21 |

Four nations, 60 rounds, 80 seeds: 70 round limit, 10 domination (rounds 7, 9,
14, 15, 18, 18, 20, 21, 26, 43), 0 economy; the countdown started once.

Trials in memory, not in the rules (scripts not kept, the numbers are for the proposals):

| change | effect, same seeds |
|---|---|
| domination only with 2 cities per nation (D-137) | 4 nations, 60 rounds: 7 dominations, from round 18 on (was from round 7) |
| food-short region: one plains instead of a forest (D-138) | food-short rank 2.64 -> 2.33 (4 nations), 3.30 -> 3.06 (5), 3.92 -> 3.79 (6) |
| gold-short region: one river instead of a hills | gold-short rank 2.85 -> 2.81 (4), 3.20 -> 3.23 (5): no effect, not proposed |

## After the rule changes (Throne of Tokens version 2)

Lead accepted D-137 (domination only once the world has 2 cities per nation) and
D-138 (one plains for a food-short start region) on 2026-11-12. The same sweep, same
seeds, bots only, on version 2:

| table | matches | round limit / domination / economy | mean rounds | dropped orders | countdown reached (best) | eliminated | neutral cities | barbarian conquests | median score gap 1st-2nd |
|---|---|---|---|---|---|---|---|---|---|
| 4x60 | 20 | 16 / 3 / 1 | 53.0 | 2.2% | 1 (5) | 0.15 | 0.75 | 0.75 | 27.5 |
| 5x60 | 20 | 17 / 0 / 3 | 58.1 | 2.1% | 4 (5) | 0.45 | 1.45 | 1.45 | 18.5 |
| 6x60 | 20 | 18 / 0 / 2 | 59.0 | 2.8% | 2 (5) | 0.15 | 1.1 | 1.1 | 13.5 |
| 4x20 | 20 | 19 / 1 / 0 | 19.8 | 1.1% | 0 (0) | 0.15 | 0.35 | 0.35 | 11.0 |
| 5x20 | 20 | 20 / 0 / 0 | 20 | 1.2% | 0 (0) | 0.3 | 0.85 | 0.85 | 9.0 |
| 6x20 | 20 | 20 / 0 / 0 | 20 | 1.7% | 0 (0) | 0.1 | 0.65 | 0.65 | 6.0 |

Against the targets, 80 seeds each:

| Target | Before (version 1) | After (version 2) | Verdict |
|---|---|---|---|
| No domination win before round ~15, 4 nations, 60 rounds | 10 dominations, at rounds 7, 9, 14, 15, 18, 18, 20, 21, 26, 43 | 12 dominations, at rounds 12, 15, 20, 22, 24, 24, 25, 33, 33, 42, 49, 50 | Mostly met: the earliest is round 12 (was 7), the next 15; wins come later but slightly more often |
| Food-short penalty gone, 4 nations, 20 rounds (food / gold / iron / wood) | 2.64 / 2.85 / 2.20 / 2.23 | 2.45 / 3.00 / 2.17 / 2.35 | Gone with 4 nations: food sits between iron and wood |
| ... 5 nations, 20 rounds | 3.30 / 3.20 / 2.71 / 2.60 | 3.13 / 3.31 / 2.77 / 2.58 | Smaller, not gone |
| ... 6 nations, 20 rounds | 3.92 / 3.90 / 2.95 / 3.16 | 3.66 / 3.93 / 3.08 / 3.17 | Smaller, not gone |
| ... 4 nations, 60 rounds | 2.69 / 2.71 / 2.27 / 2.21 | 2.58 / 2.90 / 2.36 / 2.08 | Smaller, not gone |
| Still no seat bias | 4x20: 2.39, 2.59, 2.41, 2.52 | 4x20: 2.58, 2.36, 2.65, 2.39; 5x20 and 6x20 flat within 0.2 except p3 with 6 (3.81) | No consistent seat: the best seat changes from table to table |

Also new: the economic victory now happens in four-nation 60-round matches (5 of 80,
was 0), probably because food-short nations grow more. Gold-short start regions stay
the weakest (0.5 to 0.9 places behind iron- or wood-short ones); D-138 leaves them
open on purpose.
