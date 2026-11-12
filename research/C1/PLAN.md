# C1: four-nation Civ pilot, design only

No paid Civ run is approved. The live free estimate probe returned HTTP 404,
Unknown game 'civ'; the exact response is in estimate-availability.json. There
is no valid numeric estimate yet. The inspected draft #147 initial_state rejects
nonempty game settings and uses the data round limit, so the requested 20-round
preset needs a supported contract before a meaningful quote can be obtained.
Update: Civ now appears in the live game list. Draft #157 (still open when
checked) proposes `settings: {rounds: 20}`, with a normal score ending after
round 20 unless an earlier victory occurs. Wait for merge and verified deployment
before quoting that preset; the saved 404 is historical availability evidence,
not the current live game list. No 20-round price has yet been measured here.
Do not relabel a default 60-round estimate as a 20-round quote or abort a long
game at round 20 and count that as a normal terminal outcome.

The proposed baseline is four cheap models (GLM Flash, DeepSeek Flash, GPT Luna,
Claude Haiku), one fixed seed 2104001 and four cyclic seating rotations. Each
model occupies every starting position. Use the smallest supported map for four
nations, a genuine 20-round score ending, civ-p1, memory/repair/strategy/plan off.
Freeze exact provider ids, route evidence when exposed, prompt/config hashes,
output limits, timeout and deployed build before asking Lead to approve a quote.
Support flags are declarations, not empirical Civ qualification.

The current contract is one submit_orders call per living nation per round:
at most 80 base decisions across four nations and 20 rounds, plus actual retries.
This supersedes the old 240-480-call sketch in research/README.md. Elimination
or early victory reduces exposure. Do not estimate spend by scaling Werewolf
costs: Civ observations, response lengths and retry rates differ.

After deployment, free-estimate every rotated table under the real settings.
Require each quote below EUR 0.40; report all four numbers and their sum to Lead.
Lead must approve the exact stage budget, still bounded by the remaining monthly
allowance. Serial starts use the real ledger and full enforceable match bound;
no start if spent plus next bound exceeds 90% of the approved stage allowance.
Never raise EUR 0.50 per match or EUR 25 per month; hold/report at EUR 20 monthly.
An excessive quote leads to a separately approved shorter preset or revised
design, never silent truncation, token-limit tuning or cap increases.

The later 2x2 varies only strategy_text (off/v1) and private_plan (off/on), while
keeping civ-p1 context, seed, models, seating and all runtime options fixed.
Four rotations per cell give 16 planned matches, including a reusable baseline
only if its frozen implementation matches exactly; otherwise all cells are new.
These stages have no approved budget. Civ-p2 enhanced context is an independent
future factor and must not change inside this comparison. A private plan field
in submit_orders is insufficient: off must actually prevent carry-over and on
must expose it only to its owning nation. Unsupported flags block the study.

Report strategic/order-rule errors separately from malformed tools, truncation,
provider throttling/timeouts and random replacements. Refused individual orders
are counted per submitted order, not as whole-turn tool failures. Costs include
all attempts. Record score/victory, surviving cities, treaties and trade only
where engine events support them. Four matches on one map cannot rank models;
the later factorial pilot estimates paired descriptive changes and interaction,
not general causal effects across maps. Additional seed blocks and a powered
confirmatory analysis need a separate preregistration and budget.

Reviewer bot/leak checks must cover fog, public scoreboard allowlist, hidden
orders, private plans and the requested observation-size limit before spending.
No player receives spectator map/roles/orders. No qualification or Jev call is
authorized by this plan. This custom YAML is not executable generic runner input.

## Deployed 20-round free quotes (2026-11-12)

The deployed rounds setting now works. Four planned rotations of GLM Flash,
DeepSeek Flash, GPT Luna and Claude Haiku quote EUR 0.062185, 0.062360,
0.062287 and 0.062269: EUR 0.249101 total. Responses in
quotes-20-rounds.json verify cap_micro_eur 200000 for match_budget_eur 0.20.
These are estimates using other-game history, not Civ cost measurements.

Important remaining mismatch: prompt_version civ-p1 is refused as an unknown
Civ setting. Quotes therefore omit that field and use the deployed default
prompt; no claim that the final planned prompt was priced. Requote after Civ
prompt support is available. Propose a EUR 1.00 baseline-stage ceiling with
EUR 0.20 enforceable per-match bounds, serial starts and the existing 90% rule.
Lead has not approved that ceiling or a paid match. Begin with one approved
match, review reliability/cost, then decide whether to release the other three.
The historical availability/pending-contract paragraphs above describe earlier
checks and are superseded by these successful deployed rounds probes.

## Exact baseline prompt requote, deployed main 99c4ac8

The intended baseline settings are now accepted: rounds=20, civ-p1,
strategy_text off, private_plan off, answer_repair off, match_budget_eur 0.20.
The planned GLM/DeepSeek/GPT Luna/Haiku rotations quote EUR 0.061522,
0.061696, 0.061622 and 0.061605: EUR 0.246445 total. This supersedes the earlier
EUR 0.249101 default-prompt quote and closes the prompt-support prerequisite.
Saved response payloads report the effective cap as EUR 0.20. The two factor
flags are deployed, but their later factorial stages remain separately unapproved.

No model call was made. Lead still must approve the proposed EUR 1.00 ceiling
and release the first EUR 0.20-bounded match; inspect its reliability and cost
before releasing the remaining three. Freeze actual start build/config and
recheck fresh quotes/ledger before execution. These history-based estimates
remain uncertain until model-driven Civ observations exist.
