# C1: four-nation Civ pilot, design only

No paid Civ run is approved. The live free estimate probe returned HTTP 404,
Unknown game 'civ'; the exact response is in estimate-availability.json. There
is no valid numeric estimate yet. The inspected draft #147 initial_state rejects
nonempty game settings and uses the data round limit, so the requested 20-round
preset needs a supported contract before a meaningful quote can be obtained.
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
