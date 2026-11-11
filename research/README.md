# Research

How the models in the arena are evaluated: plans under
[`experiments/`](../experiments/README.md), tooling under `arena/research/`,
reports here. This page is the research plan. It holds no result yet: no
experiment has been played.

Two kinds of matches are analysed with the same tools: matches of a
registered experiment, and any match somebody starts by hand in the UI or on
the command line. Every paid run needs the project owner's own yes; he has
approved all of experiment 1: the pilot and stage A first, then B and C.

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

## Notes from matches outside the experiments

- **Poker, heads-up, deepseek-flash against gpt-luna (match 0cee2bac, played
  by the owner on 2026-11-11):** 14 of 66 answers were rejected, all of them
  gpt-luna's, none caused by the game. Three kinds: arguments with the model's
  own reasoning text inside ("} } (oops syntax) } (Malformed) {"), garbled or
  empty keys on tools that take no arguments (call, check, fold, all_in), and
  arguments that were not a JSON object. A single match, so not a finding
  about the model yet. It shows that "rejected answers" mixes format failures
  with real rule mistakes, so the analysis counts clean, repaired and
  rejected moves separately.
- **Answer repair is a setting, like the prompt version.** The arena is
  getting an optional repair of malformed tool calls. For research it must be
  chosen per match in the settings, recorded in `match_started`, and off by
  default, so that matches with and without repair are never mixed in one
  comparison. Experiment 1 runs without repair in every stage (plan version 3).

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

6. Model seats in `POST /matches`: experiment matches run through the API of
   the shared stack, one at a time, so that they can be watched live and one
   ledger counts every call.

Built here, under `arena/research/`: the export, the batch runner, the
analysis and the reports (steps below).

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
| E1 stage A: pilot of the 8 cheap models (played: 6 matches, 0.23 EUR, stopped by the budget rule; league dropped in version 2) | 6 | 0.30 | 0.30 |
| E1 stage A2: league of the 6 models that passed the pilot (approved) | 120 | 2.40 | 3.00 |
| E1 stage B: one model at high and low reasoning effort (approved, after A) | 96 | 4.20 | 4.50 |
| E1 stage C: 4 stronger models as guests among cheap hosts (approved, after A) | 96 | 7.20 | 7.50 |
| Poker in duplicate mode, cheap roster (own plan, later; not approved) | 48 | 2.60 | 2.80 |
| Not assigned | | | 1.72 |
| Reserve, 20 % | | | 5.00 |
| **Sum** | | | **25.00** |

How the estimates were made: calls per match from the example match and the
bot matches (40 per Liar's Deck match), about 2 500 input and 700 output
tokens per call at low effort (from the example matches' cost), 4 000 output
tokens at high effort (an assumption; stage B's first replicate measures it),
times the listed prices. A stage stops at its budget, whatever the estimate.

Why Liar's Deck first: it is the cheapest and fastest game with four seats, a
match has one winner and a full order of places, and its skills (lying,
calling) can be counted from the log without a judge model. Poker follows,
because duplicate mode removes most of the card luck. Werewolf comes after
that: results are per team, so a model needs many matches per role.

Later, once the arena supports them: memory on against memory off, and
Throne of Tokens.

## Proposal: prompt p1 against p2 (not approved, no spend)

The prompt pack v2 (pull requests #65, #66, #68) gives every game a second
prompt: new rules text and a situation summary built from the observation.
`prompt_version` is a setting of the whole match, so all four seats read the
same version. That decides the design:

- **Version per match (possible once the runner passes settings):** stage A of
  experiment 1 runs with p1. Afterwards the same 56 seed and seating
  combinations of its first replicate are played again with p2. Each p2 match
  has a p1 twin with the same cards and the same seats, so the comparison is
  paired. Outcomes: rejected answers and fallback turns per move, call
  accuracy, lie rate, and whether a model's rank changes. Win shares cannot
  move as a whole, because every seat has the same prompt. About 1.10 EUR
  (56 matches at stage A's cost per match), budget 1.30 EUR, from the
  unassigned 2.02 EUR. Test: Wilcoxon signed rank on the paired per-match
  fallback rate, two-sided; the rest as effect sizes with intervals.
- **Version per seat (needs the arena to take settings per seat):** the
  mirror design of stage B with p1 and p2 instead of two efforts. Only that
  says whether p2 makes a model win more. Planned when the arena supports it.

Experiment 1 itself stays on p1 in all stages, passed explicitly, so its
results compare with the matches already played.

Seen by Arena Coder while writing v2: the Werewolf rules of p1 do not name
the tools `stay_in_bed` and `let_them_die`. That is a likely cause of tool
errors in Werewolf and a confound for any Werewolf comparison across the two
versions.

## Proposal: a short headline next to the thought (p3, not approved, no spend)

Viewers read long thoughts badly. Prompt version `<game>-p3` would ask for a
required `headline` (at most 15 words) next to the private `thought` in every
tool call; the UI shows the headline and keeps the full thought one click away.
Until p3 exists the UI takes the first sentence of the thought.

What could go wrong, and so what the pilot measures: one more required
argument may make weak models fail tool calls more often, cost more output
tokens, or change how they play.

- **Design:** the prompt version is set per match, so p3 is compared with p1 on
  the same seeds and seatings: the first 24 matches of league A2 (the 6 clean
  models, Liar's Deck) are played again with p3. Each p3 match has a p1 twin
  with the same cards and seats.
- **Outcomes, per model and pooled:** rejected answers per move, share of
  moves played by the fallback, output tokens and response time per move, cost
  per match. As a check on play: lie rate and call rate. Win shares cannot
  move, because every seat reads the same prompt.
- **Test:** Wilcoxon signed rank on the paired per-match rejected answers per
  move, two-sided, alpha 0.05; the rest as paired differences with bootstrap
  intervals over matches. The pilot is a safety check: with 24 pairs it finds
  only large changes, and "no change found" is not "no change".
- **Stop rule:** p3 does not become the default if the fallback share of any
  model rises above 10 % or the pooled rejected answers per move rise by more
  than 0.1.
- **Cost:** about 0.50 EUR (24 matches at league A2's 0.02 EUR each, plus a
  margin for the extra tokens); budget 0.60 EUR from the unassigned 1.72 EUR.
  Needs the owner's yes. Werewolf, where headlines matter most, follows only
  after the two weak models are fixed, because a full table needs 8 clean
  models.
- **Needs from the arena:** `headline` as a required argument in the tool
  schema for p3 (Builder), recorded in the `thought` event next to the text.

## Build steps

One step is one branch and one draft pull request, tested on bot and mock-LLM
matches, without a paid call. Every command works on whatever matches are in
the database or in saved files, not only on experiment matches.

| Step | Content |
| --- | --- |
| R1 (this one) | Plan format and loader, seatings, schedule, power; plan of experiment 1. |
| R2 | `arena research export`: all or filtered matches as flat tables (matches, players, turns, events, thoughts and messages, tool calls, costs and tokens, statistics per game) in CSV, JSON and one SQLite file; the schema in `research/DATA.md`. |
| R3 | Batch runner as a client of the arena API: plays a schedule one match at a time, prints the live address of each match, pauses between matches, resumes after a stop, enforces the run budget (stop at 90 %) and the pilot rule. Tested with bot seats. |
| R4 | Leaderboard with intervals: win share (Wilson), mean rank, Plackett-Luce strengths and Elo with bootstrap intervals; head-to-head matrix; seat effects; the permutation tests of the plan with Holm correction. |
| R5 | Views over time: learning curves and variance per model, by seed and by date. |
| R6 | Play style: features per model and game (lie and call rates, risk taken against the revolver or the pot odds, aggression, timing of deception, voting), with intervals; which models play alike (clusters, nearest neighbours), outliers, notable moments. |
| R7 | Failure modes: ignored tools, repeated rejected answers, timeouts, fallbacks, cut-off answers, per model. |
| R8 | Thoughts against words: rule-based contradiction checks per game; a judge model only with its own approved budget. |
| R9 | Report generator: Markdown with figures per model and per game, methods and limits, model ids, dates, commit. |
| R10 | `research/GUIDE.md`: how to design and run an own experiment (plan template with comments), estimate its cost before the run, export, analyse and read the report. |
| R11 | Paper skeleton under `research/paper/`. |
