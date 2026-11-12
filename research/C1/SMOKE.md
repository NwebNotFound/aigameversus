# C1 first smoke: halted by the reliability gate

The one approved direct match `f12a97d0-458a-4025-8c98-ced72baa6acc` was paused
and then aborted by Researcher after DeepSeek exceeded the 10% fallback gate.
It cost **EUR 0.011856**, below the EUR 0.16 smoke ceiling. The month ledger is
EUR 3.768135. No additional C1 rotation is released; there was no tuning or rerun.
This is an incomplete three-round opening, not a completed 20-round match.

| Model | Observed decisions | Bot replacements | Rejected answers | Output cutoffs | Ledger EUR |
| --- | ---: | ---: | ---: | ---: | ---: |
| GLM Flash | 3 | 0 | 0 | 0 | 0.000584 |
| DeepSeek Flash | 3 | 2 (66.7%) | 6 | 6 | 0.007564 |
| GPT Luna | 3 | 0 | 0 | 0 | 0.001609 |
| Claude Haiku | 3 | 0 | 0 | 0 | 0.002099 |

DeepSeek's first two turns each exhausted three model responses at 1,500 tokens
without reaching a tool call. Each response's output budget was entirely used
for reasoning. Its third turn produced an accepted call. Across seven answers it
used 10,257 output tokens, 10,125 recorded as reasoning. Thus the observed failure
is output/reasoning-budget exhaustion under this game/configuration, not evidence
that the model cannot use tools. No provider rate-limit explanation is needed
for those six rejections. No agent permanently failed.

The safety pause request succeeded; an already active round completed before the
pause took effect, so final exposure is three decisions per seat. Researcher then
aborted the paused game to end the failed smoke and leave no running paid match.
Every accepted/bot move and charged call remains in the log. Pausing is not an
instant cancellation of every in-flight request. No remaining rotation started.

## What the opening shows about play

GLM and GPT moved their initial settler armies away from their capitals and each
founded a second city in round three. Their explanations explicitly connected
expansion to later domination/score and planned movement before settlement.
Haiku built its economy and recruited another settler. These are examples of
short multi-turn expansion plans, not evidence that every model only considers
the immediate turn. Three opening rounds cannot establish strategic strength,
long-run diplomacy, war quality or a model ranking.

There were **three individual order refusals**, distinct from the six rejected
model responses: Haiku and GLM each tried to train a spearman after earlier
spending left insufficient wood; GLM also sent a build order without its city id.
The outer submit_orders call was accepted in those cases, while the game refused
the individual invalid order. This suggests a useful future checklist for total
batch affordability and required entity ids. It does not authorize changing p1
or retuning the current stage. DeepSeek's two fallback actions were random bot
orders and must never be interpreted as its strategy.

## Context, provenance and limits

Frozen before first response: plan commit `a6eac5a`, roster GLM/DeepSeek/GPT
Luna/Haiku, seed 2104001, 20 rounds, civ-p1, strategy/private-plan/repair off,
memory false. Actual call options were read inside the deployed container:
1,500 output tokens, low reasoning, required tool choice for all four models.
The enforced per-match budget was EUR 0.20. Fresh quotes for all four rotations
totalled EUR 0.293283; those remain history-based estimates, not completed-Civ
cost measurements.

Build: Reviewer-reported main `01e8b50`, image digest and raw-export SHA-256s in
smoke-provenance.json. The live Civ history window was independently read back
as 120. Only 114 events exist in the complete aborted log, including spectator-
only engine events, so no player's event list could reach that window. There is
no evidence of the old 40-event history cut in this smoke. The observed cutoffs
are output-length failures, a different mechanism. Exact outbound model requests
are not saved, so this is a bounded event-window audit, not a claim to inspect
every byte delivered by the provider. Raw events/transcript remain local; the PR
contains aggregates and hashes, not a portable raw dataset.

The sample is one partial match, with unequal game histories caused by fallback
orders. Do not infer a general Civ pass from the other models' three valid
decisions, or a model-family failure from DeepSeek's configuration. The C1 gate
failed; any remediation requires a separate version/configuration and explicit
approval. Werewolf qualification and guest-stage release are separate decisions.

Readable transcript (local arena):
[full Markdown transcript](http://localhost:8100/matches/f12a97d0-458a-4025-8c98-ced72baa6acc/transcript?format=markdown&spoilers=true).
The [spectator page](http://localhost:3100/matches/f12a97d0-458a-4025-8c98-ced72baa6acc)
also retains the aborted replay. These localhost links are for the arena host;
phone reachability is not established by this report.
