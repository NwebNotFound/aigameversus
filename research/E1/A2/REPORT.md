# E1, stage A2: a Liar's Deck league of six cheap models

Plan: [experiments/E1_liars_deck.yaml](../../../experiments/E1_liars_deck.yaml), version 3.
Data: 120 matches played on 2026-11-11 between 21:15 and 23:13 UTC through the arena API.
Numbers: [results.json](results.json), produced by `python -m arena.research.analysis runs/E1-A2 --out research/E1/A2`
(analysis committed in b878b80 while the league was still running, before any outcome was read).

## Conditions

| | |
| --- | --- |
| Game | Liar's Deck, base variant, 4 seats |
| Models | gpt-luna, claude-haiku, glm-flash, deepseek-flash, mistral-small, llama-scout (OpenRouter ids and prices in the plan) |
| Design | all 15 tables of four, each with 2 seeds and 4 seatings: 120 matches, 80 per model, 20 per model and seat, 48 match meetings per pair. All 120 cells were played once, none replayed. |
| Prompt | `liars_deck-p1`; memory off; reasoning effort low; output limit 1 500 tokens; no answer repair |
| Arena | stack aff3a8a for matches 1-68, b3afda0 after a planned rebuild (rules and prompt unchanged) |
| Cost | 2.4749 EUR (0.0206 per match) of a 3.00 EUR run budget |

## Results

**H1: the six models are not equally strong. Supported.** Permutation test of the mean ranks,
p < 0.0001 (100 000 permutations; none as extreme); Holm over the confirmatory family: p < 0.0001.

**H2: win share against 1/4 (Holm over 6), and Plackett-Luce strength (bootstrap over seeds).**

| Model | Wins | Share | 95 % interval | p (Holm) | Strength | 95 % interval |
| --- | --- | --- | --- | --- | --- | --- |
| glm-flash | 48 / 80 | 0.60 | 0.49-0.70 | < 0.0001 | +1.27 | +1.01 to +1.61 |
| deepseek-flash | 43 / 80 | 0.54 | 0.43-0.64 | < 0.0001 | +0.99 | +0.60 to +1.47 |
| gpt-luna | 16 / 80 | 0.20 | 0.13-0.30 | 0.37 | +0.21 | -0.01 to +0.44 |
| mistral-small | 7 / 80 | 0.09 | 0.04-0.17 | 0.0008 | -0.53 | -0.78 to -0.33 |
| claude-haiku | 3 / 80 | 0.04 | 0.01-0.11 | < 0.0001 | -0.86 | -1.19 to -0.59 |
| llama-scout | 3 / 80 | 0.04 | 0.01-0.11 | < 0.0001 | -1.09 | -1.45 to -0.74 |

Two models win far more than chance, three far less; gpt-luna is not distinguishable from
chance. The cheapest model per token (glm-flash) is the strongest here.

**H3: models call "Liar!" more often on lies than on honest plays. Supported overall, not for
every model.** Pooled Mantel-Haenszel odds ratio 1.41, p = 0.0006. Per model (call opportunities
facing a lie / facing an honest play; the model's own moves only):

| Model | Calls on lies (hit rate) | Calls on honest plays (false alarms) | Odds ratio | p (Holm) |
| --- | --- | --- | --- | --- |
| glm-flash | 66 / 169 = 0.39 | 101 / 485 = 0.21 | 2.44 | < 0.0001 |
| deepseek-flash | 52 / 144 = 0.36 | 87 / 451 = 0.19 | 2.36 | 0.0003 |
| claude-haiku | 38 / 49 = 0.78 | 233 / 309 = 0.75 | 1.13 | 1 |
| mistral-small | 68 / 100 = 0.68 | 264 / 369 = 0.72 | 0.85 | 1 |
| llama-scout | 19 / 35 = 0.54 | 156 / 268 = 0.58 | 0.85 | 1 |
| gpt-luna | 25 / 91 = 0.27 | 142 / 420 = 0.34 | 0.74 | 1 |

Only the two winning models tell lies from honest plays. claude-haiku and mistral-small call
three times in four whatever is on the table, which costs them trigger pulls; this is a likely
reason for their low win shares (an observation, not a registered test).

**H4: the seat does not change the chance to win. Not rejected.** Winners by seat p1-p4: 25, 31,
36, 28; chi-square 2.2, p = 0.55 (Monte Carlo). The seat rotation worked as intended.

## Reliability (all moves; no answer repair)

| Model | Clean moves | Rejected answers per move | Moves played by the fallback | Failed agents |
| --- | --- | --- | --- | --- |
| gpt-luna | 100 % | 0.00 | 0 % | 0 |
| claude-haiku | 100 % | 0.02 | 0 % | 0 |
| glm-flash | 99.9 % | 0.02 | 0.1 % | 0 |
| llama-scout | 99.6 % | 0.22 | 0.4 % | 0 |
| mistral-small | 99.5 % | 0.24 | 0.5 % | 0 |
| deepseek-flash | 95.3 % | 0.54 | 4.7 % | 0 |

deepseek-flash wins often despite the most corrections; its rejected answers are mostly answers
cut off at the output limit. All six stay under the plan's 10 % fallback rule.

## Limitations

- One game, one variant, one prompt version (p1), low reasoning effort and a 1 500-token output
  limit; the ranking may differ with more thinking (stage B) or another prompt.
- Moves played by the fallback count as the model's play (intention to treat); deepseek-flash has
  4.7 % such moves, the others under 1 %. A sensitivity run without them is still to do.
- Matches on one seed share cards; intervals for strengths resample whole seeds.
- The two models that failed the pilot (qwen-flash, gemini-flash-lite) are not in this league.
- Exact model ids, prices and dates are in the plan; the arena commits are in the run folder.

## Not yet done

Sensitivity analysis without fallback moves; lie rates and chosen-lie rates per model; stage B
(effort) and stage C (stronger guests), both approved, not started.
