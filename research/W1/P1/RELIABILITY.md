# W1 P1: reliability gate

2026-11-12. Eight of eight classic 8-seat Werewolf matches completed on stack
db77cbe, werewolf-p2, low reasoning, memory off, answer repair unavailable/off.
Batch W1-P1. Total ledger cost EUR0.334566 of EUR1.00; no failed/interrupted
match and no agent failure. This report examines reliability only, not outcomes.

| Model | Distinct matches | Seat appearances | Decisions | Bot replacements | Rejected answers |
| --- | ---: | ---: | ---: | ---: | ---: |
| glm-flash | 8 | 8 | 69 | 0 | 6 |
| deepseek-flash | 8 | 8 | 67 | 2 (2.99%) | 23 |
| gpt-luna | 8 | 16 | 151 | 0 | 1 |
| mistral-small | 8 | 8 | 62 | 0 | 1 |
| llama-scout | 8 | 8 | 35 | 6 (17.14%) | 27 |
| claude-haiku | 8 | 16 | 140 | 0 | 2 |

Decision denominator is action_accepted plus action_fallback, including talk;
rejections are attempted answers, so several can belong to one decision. GPT and
Haiku each hold two seats, not sixteen independent matches. Across all seats:
524 decisions, eight bot replacements, 60 rejected answers.

## Cause and decision

All 27 Llama rejections exceed the game's word limit (40-word short actions or
120-word speeches). Some retries remain far above the limit. These are legal
tool calls with invalid speech length, not evidence of absent tool support.
Increasing its output token allowance would not address the observed violation.

DeepSeek has 21 length cutoffs, one 121-word speech (limit120), and one speak
call missing text. The other cutoff is Mistral's. GLM's six, Haiku's two and
GPT's one rejection are overlong speech. Totals: 37 speech-length errors,
22 output cutoffs and one required-argument error. These labels come from the
recorded validator messages; old logs have no new per-decision cutoff counters.

**P1 fails its pre-registered reliability gate:** Llama exceeds10% bot moves;
all other models remain below10% and no model has failed in two matches.
P2, P3 and strong guests have not started. Lead decision01bebc80 subsequently
omits Llama from P2/guest rosters and grants P3 an explicit remediation exception
with original seats retained (plan v4). No silent substitution, weakened
threshold or repeat-until-pass. Original P1 remains intact and all failures count.

Descriptive reliability sensitivity: including all seats gives8/524 bot decisions
(1.53%) and60/524 rejected answers per decision (0.115); excluding Llama's seat
records gives2/489 bot decisions (0.41%) and33/489 rejected answers per decision
(0.067). Opponents still faced Llama in these games; this exclusion cannot tell us
what would happen in games played without Llama. It does not change the original
gate failure, team outcomes or recorded costs. Outcome sensitivity remains to be
computed with the outcome report, without inventing counterfactual wins.

Recommended options for Lead: fix/requalify Llama under an approved configuration,
or omit it from a newly amended P2/guest roster. P3 was paired to the original
P1 seats: changing that roster loses the planned pairing. A deliberately
approved p3 reliability-remediation stage retaining those seats would require
an explicit amendment to the clean-P1/P2 gate, before inspecting outcomes.

## Next-stage constraints

Additional speech/vote/privacy audit: all250 accepted text actions (238 speeches,
12 wolf chats) and114 accepted vote reasons fit their applicable120/40-word limits; all114 day votes
target a living player or legal null at that event. No night action was rejected
for an invalid target or role. Stored role assignment, pack, seer/witch and thought
audiences passed the targeted privacy checks; wolf event audiences were subsets
of the pack. The model path filters events by player visibility before building
the request, and Werewolf observations gate pack/seer/potion fields by role.

No literal `I am pN` self-seat mismatch was found (there were no such explicit
self-seat statements). This is a narrow syntactic scan, not a semantic finding
that no identity confusion occurred. Exact sent model-request snapshots were not
logged; no claim of exhaustive absence of leaks is possible from spectator logs.
No public role claim was treated as a leak merely because it matched ground truth:
players may reveal their own role, infer another's role or deceive.

Accepted actions also include17 seer checks,44 wolf kill choices,18 witch actions,
six hunter shots,60 captain election votes and seven captaincy transfers. These
counts establish exercised action paths, not strategic quality. Machine-readable
checks: speech_privacy.json; reproducible script: research/W1/speech_privacy.py.

Free local regression checks:64 tests passed in games/werewolf/tests/test_matches.py,
games/werewolf/tests/test_plugin.py and tests/agents/test_prompt.py, including
role-private observation/event-audience checks. These exercise the local research
checkout; they are not captured requests from the historical deployed model run.

Reviewer was asked to use the now-idle gap for a controlled rebuild. The old
db77cbe container exposes only werewolf-p1/p2, so it cannot run P3 yet. Future
matches must explicitly keep answer_repair off if the rebuilt version offers it.
Record the actual rebuild/config; a new runtime introduces a limitation for the
paired P3 comparison even if the game engine and p2 text are unchanged.

P2 and P3 each have EUR0.50 stage budgets. With only a server-enforced EUR0.50
per-match cap, reserving a whole match permits one match initially, then the
remaining stage allowance is below that worst-case bound. A EUR0.04 estimate is
not an enforceable cap. More starts require a smaller enforced match/run limit
or a revised allocation by Lead; never silently risk exceeding stage budgets.

Evidence: runs/W1-P1/001.json through008.json, runs.jsonl, runtime.json,
GET /batches/W1-P1 and cost endpoints. Counters in reliability.json; extraction
script saved at research/W1/reliability.py. No ledger edits, no model calls for
analysis, no win-rate or strategic conclusions from this gate report.
