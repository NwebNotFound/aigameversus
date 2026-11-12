# W1 cheap Werewolf pilots: closure and remediation result

2026-11-12. Plan v5 closes P1/P2/P3. This is a descriptive pilot on one scenario
seed per stage, not a model ranking or a definitive prompt-effect experiment.
No Jev calls or additional game calls were made for analysis.

| Stage | Completed / planned | Ledger cost | Prompt | Disposition |
| --- | ---: | ---: | --- | --- |
| P1 | 8 / 8 | EUR 0.334566 | werewolf-p2 | Llama failed reliability gate |
| P2 | 1 / 8 | EUR 0.067841 | werewolf-p2 | Closed by Lead after Qwen timeouts |
| P3 | 6 / 8 | EUR 0.309660 | werewolf-p3 | Budget reservation stop; Llama still fails |

All 15 started matches finished; no failed/interrupted match or failed agent was
recorded. W1 total: EUR 0.712067; month ledger at closure: EUR 3.756279 of 25.00.
P3 had EUR 0.190340 left, less than its full EUR 0.20 enforceable next-match bound.
The runner stopped safely rather than betting on the lower mean/estimate.
The arena cap has since been restored to EUR 0.50, independently read back.

## P2 is one observation, not a qualification pass

Lead decision `7e2c9806` closes P2 permanently as n=1. Llama's entry was replaced by
gpt-luna before P2; two GPT seats do not create two independent matches.

| Model | Decisions | Bot replacements | Rejected answers |
| --- | ---: | ---: | ---: |
| qwen-flash | 15 | 4 (26.67%) | 0 |
| gemini-flash-lite | 7 | 0 | 1 (word limit) |
| gpt-luna, both seats | 20 | 0 | 0 |
| glm-flash | 10 | 0 | 1 |
| deepseek-flash | 10 | 0 | 3 |
| mistral-small | 6 | 0 | 0 |
| claude-haiku | 6 | 0 | 0 |

Every Qwen replacement followed a 60-second timeout (60,002-60,003 ms), rather than
a malformed or rejected tool call. Qwen also produced 11 accepted actions: tool
support is not disproven. Under this route/config, however, it exceeds the
pre-registered 10% fallback gate and is excluded from subsequent Werewolf/guest
rosters until a mini qualification after separate configuration work. Do not tune
it inside W1 or extrapolate from one match to the whole model family. Gemini's
seven decisions are insufficient to establish reliability across roles.

## Primary remediation comparison: Llama still fails

Use only the six P1 cells with actual P3 twins, matched by seed, seating and full
roster. Comparing all eight P1 cells directly with six P3 cells would mix exposure.

| Llama metric | P1 six matched cells | P3 six matched cells |
| --- | ---: | ---: |
| Decisions | 24 | 53 |
| Bot replacements | 5 / 24 (20.83%) | 11 / 53 (20.75%) |
| Word-limit rejected answers | 19 | 53 |
| Word-limit rejected answers per decision | 0.792 | 1.000 |

These are pooled descriptive ratios, not an equal-weight paired effect estimate.
One matched P1 cell had zero observed Llama decisions; its individual
fallback rate is undefined. Exposure changes as the games develop. On the full
P1 stage the Llama rate was 6/35 = 17.14%; this is not the matched baseline above.

All 53 P3 Llama rejections were overlong text/reasons. The revised word budgets
did not bring its observed replacement rate below 10%. This is a failed
remediation gate, not proof that the prompt has zero effect. The two unplayed
P3 cells remain missing; Llama is not re-qualified and is excluded from guests.

| Other model, P3 | Decisions | Bot replacements | Rejected answers |
| --- | ---: | ---: | ---: |
| gpt-luna, both seats | 101 | 0 | 0 |
| claude-haiku, both seats | 106 | 0 | 1 |
| glm-flash | 47 | 0 | 1 |
| mistral-small | 37 | 0 | 2 |
| deepseek-flash | 62 | 1 (1.61%) | 23 |

DeepSeek's 23 rejections include 18 output cutoffs and five other argument/format
errors. Mistral has one cutoff and one other error. Low replacement share can
therefore coexist with substantial retries, delay and cost.

## Descriptive game outcomes

P1 wolves won 5/8 and village 3/8; P2's sole village win supports no inference;
P3 wolves won 4/6 and village 2/6. In the matched six P1/P3 cells: two wolf wins
stayed wolf wins, two changed wolf-to-village, two village-to-wolf. Village wins
are 2/6 on each side. The sample cannot establish that one prompt wins more.

Village model-controlled non-abstaining votes targeted a true wolf 24/77 times in
P1 (31.17%), 10/14 in the single P2 match and 22/62 in P3 (35.48%). These stage totals
are **not** a paired causal comparison. Bot-controlled votes and abstentions are
stored separately and excluded from these ratios. They are not independent
trials: multiple votes come from the same match/role/seed. We report counts rather
than misleading confidence about general win/role strength from one seed.

Per-model role appearances/wins are in results.json. GPT/Haiku seats share match
outcomes; do not treat their 16 P1 appearances as 16 independent matches. No Elo or
role ranking is warranted by this small, incomplete pilot. Speech influence,
seer first-public-result timing and subjective lie detection remain unmeasured
here; the code does not invent semantic labels from successful votes or role truth.

## With/without Llama sensitivity

P1 decision reliability including all seats: 8/524 bot moves (1.53%); excluding
Llama's seat records:2/489 (0.41%). These games still contained Llama and its effect
on opponents. Removing its table row changes the cohort, not what happened.
The JSON also exports per-model/role views; excluding Llama leaves other models'
recorded wins unchanged. Removing every whole game containing Llama leaves zero
P1 and zero P3 games, so no counterfactual team result or Elo can be estimated.
This sensitivity never reverses the original Llama failure or changes ledger cost.

## Methods, provenance and limits

Reproduce from saved exports with:

```bash
python -m arena.research.werewolf_pilot PATH_TO_RUNS --out research/W1/summary
```

Source: finished last-attempt cells in W1-P1/P2/P3 runs.jsonl and matching event
exports. Cost sums every logged attempt. Decisions=accepted+fallback; retries
remain rejected answers, not extra turns. Vote classification uses initial roles
in the classic template and the immediately preceding action's bot/model origin.
The initial outcome-analysis implementation was committed as `6c9c9a3` before its
first run on team/role outcomes; subsequent edits made zero counters explicit and
added descriptive paired team transitions after results were seen. No threshold,
cell selection or primary reliability metric changed.
provenance.json lists the raw export ids, timestamps and SHA-256 digests plus
the analysis-file digest. Raw event exports remain in the local runs folders;
this PR contains aggregates and provenance, not a portable public raw dataset.
Exact OpenRouter model ids and configured prices are frozen in the linked plan.

P1: `db77cbe`, cap 0.50, p2, memory off, repair unavailable/off. P2 match 1: reported
`da0721f`, cap 0.50, p2, repair explicitly off. Its captured old digest is no longer
inspectable; source mapping rests on Reviewer statements, saved lock notes and
rebuild timestamps, not cryptographic image-to-commit proof. P3: `46c5d6c` plus the
local cap 0.20 override, p3, repair/memory off. The digest and start estimate/cap/
month checks were captured in run.json/start_checks.jsonl. Different build/cap
are confounds; none of the completed P3 matches reached its cap. Post-stage
restore: main `87fcf21`, cap 0.50. No engine or prompt text was changed mid-stage.

The original schedule is preserved. P2 stopped by a reliability decision; P3
stopped by a monetary bound, so missing cells are not a random sample. Results
describe these routes/configurations and scenario cells, not inherent model
capability or the benefit of extra thinking. All original errors/bot moves count.
