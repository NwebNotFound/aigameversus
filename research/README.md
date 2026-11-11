# Research

How the models in the arena are evaluated: plans under
[`experiments/`](../experiments/README.md), tooling under `arena/research/`,
reports here. This page is the research plan. It holds no result yet: no
experiment has been played.

State: 2026-11-11, `main` at `b8dc53e`.

## What the arena can run today

| Topic | State |
| --- | --- |
| Games | Liar's Deck (2-4 seats), Poker (2-6), Werewolf (6-16) finish with random bots and have each been played once or twice by real models. Throne of Tokens has no plugin yet. |
| Seats with models | `arena run --game G --models a,b,c --seed N --save FILE`: one model per seat, in that order. The API seats bots only. |
| Seeds | One seed fixes cards, revolvers and roles. The luck belongs to the seat (`p1`, `p2`, ...), not to the model, so the same seed with another seating gives another model the same luck. |
| Seat rotation | By the order of `--models`. Poker also has `duplicate` (same cards, rotated seats). No batch runner. |
| Blinding | Prompts say `player p1`; no model name reaches a prompt. |
| Memory | No memory reaches a prompt on `main` (a pull request for it is open), so every match is "memory off". |
| Thinking | One global `reasoning_effort` (`low`) and one output limit (1 500 tokens) for all models. No temperature is set. |
| Ledger | Every call is booked in `model_calls` (tokens, cost, time of the call) against 0.50 EUR per match and 25 EUR per calendar month. |
| Export | `--save` writes seats, result, cost per seat and all events, thoughts included. No time stamps, tokens or provider per call. |
| Statistics | `arena/stats/`: lie rate, calls and call accuracy (Liar's Deck); VPIP, aggression, bluffs, chips per 100 hands (Poker); vote accuracy, seer survival (Werewolf). Multiplayer Elo in `arena/ratings/`. No intervals, no tests. |

What the three example matches in `docs/examples` say about cost and
reliability (one match each, so only a rough guide):

| Game | Model calls | Cost | Rejected answers | Turns played by the fallback |
| --- | --- | --- | --- | --- |
| Liar's Deck, 4 seats | 31 | 0.012 EUR | 2 | 2 (one seat failed at its first call) |
| Poker, 6 seats, 20 hands (before the answer format changed) | 136 | 0.054 EUR | 30 | 5 |
| Werewolf, 8 seats | 66 | 0.041 EUR | 14 | 1 |

A call cost 0.0001 to 0.001 EUR with the cheap roster. Random bots need about
42 moves for a Liar's Deck match (4 000 matches, 5 % to 95 %: 19 to 69) and win
24.1, 24.2, 26.0 and 25.7 % of them from seats `p1` to `p4`.

## What blocks serious experiments

Needed from the arena core (Arena Builder), most of it already planned:

1. A budget per run (the monthly cap of 25 EUR is in the config since D-076).
2. Reasoning effort and output limit per seat. At 1 500 output tokens a model
   at high effort is cut off before its move. The same model must be able to
   sit in several seats with different settings.
3. Stronger models in the roster (ids and prices in the plan of experiment 1).
4. Per call in the export or a run summary: seat, model, effort, tokens in and
   out, duration, outcome (accepted, rejected, fallback), and the provider
   that served it. Without duration there is no latency; without tokens no
   check that "high effort" was really more thinking.
5. The commit of the arena in every saved match, as the prompt version.

Built here, under `arena/research/`: the batch runner, the analysis and the
reports (steps below).

Known limits that stay and are reported with every result: a prompt shows the
last 40 events only; sampling is the provider's default; one model id can be
served by several providers; prices in the ledger are upper bounds.

## Experiments and budget

The monthly cap is 25 EUR (set by the project owner on 2026-11-11); 0.18 EUR
were spent before this plan, as Arena Lead reports from the ledger. A fifth of
the cap stays unplanned.

| Line | Matches | Estimate | Budget |
| --- | --- | --- | --- |
| Spent before | 6 | | 0.18 |
| E1 stage A: league of the 8 cheap models, Liar's Deck | 112 | 2.20 | 3.00 |
| E1 stage B: one model at high and low reasoning effort | 96 | 4.20 | 5.00 |
| E1 stage C: 4 stronger models as guests among cheap hosts | 96 | 7.20 | 8.00 |
| E2: Poker in duplicate mode, cheap roster (own plan, later) | 48 | 2.60 | 2.80 |
| Not assigned | | | 1.02 |
| Reserve, 20 % | | | 5.00 |
| **Sum** | | | **25.00** |

How the estimates were made: calls per match from the example match and the
bot matches (40 per Liar's Deck match), about 2 500 input and 700 output
tokens per call at low effort (from the example matches' cost), 4 000 output
tokens at high effort (an assumption; stage B's first replicate measures it),
times the listed prices. A stage stops at its budget, whatever the estimate.

Why Liar's Deck first: it is the cheapest and fastest game with four seats, a
match has one winner and a full order of places, and its skills (lying,
calling) can be counted from the log without a judge model. Poker follows as
E2, because duplicate mode removes most of the card luck. Werewolf comes after
that: results are per team, so a model needs many matches per role.

Later, once the arena supports them: memory on against memory off, and
Throne of Tokens.

## Build steps

One step is one branch and one draft pull request, tested on bot and mock-LLM
matches, without a paid call.

| Step | Content |
| --- | --- |
| R1 (this one) | Plan format and loader, seatings, schedule, power; plan of experiment 1. |
| R2 | Batch runner: plays a schedule match by match through the arena's `Budget`, resumes after a stop, enforces the stage budget and the pilot rule, writes one saved match per line of the schedule and a run log. Tested with bots and the mock LLM. |
| R3 | Data set: saved matches to tidy tables (matches, seats, moves, calls) as CSV, with reliability and cost per seat. |
| R4 | Outcome statistics: win share with Wilson intervals, mean rank, the permutation tests of the plan, Holm correction, seat and seed effects. |
| R5 | Ratings: Plackett-Luce strengths and Elo with bootstrap intervals over whole seeds. |
| R6 | Game skills with intervals: Liar's Deck first (lie rate, call accuracy and its 2x2 test, bluffing against revolver risk), then Poker and Werewolf. |
| R7 | Thoughts against words: rule-based checks per game; a judge model only with its own approved budget. |
| R8 | Report generator: Markdown, CSV and figures per experiment, one page per model, methods and limits, model ids, dates, commit. |
| R9 | Paper skeleton under `research/paper/`. |
