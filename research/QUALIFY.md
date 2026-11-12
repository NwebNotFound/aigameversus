# Model qualification protocol

Design v1, 2026-11-12. Owner: Arena Researcher. Implementation: Arena Coder Heavy,
after Werewolf/Civ work; runner/ledger changes remain Arena Builder's. This document
authorizes no paid calls. No mass qualification without Nils' budget approval.

## Purpose and scope

Test whether one exact model/provider/game/configuration can produce legal actions
through the real arena request path. Separate compatibility, availability, output
limits and latency from strategic quality. Qualification is not a strength rating
or a guarantee that future calls work. Never award qualification from catalog tool
metadata, a bot fallback, a repaired response, or another game's results alone.

Two scopes prevent a small test from overstating coverage:

- **Core pre-flight:** 3-6 scripted real requests per game, from deterministic,
  isolated fixtures. The picker can say `qualified: core (5/5 checks)` only for
  that scope; uncovered roles/actions remain explicitly unknown.
- **Extended coverage:** additional approved requests covering every enabled role
  action/order type and relevant boundary. The picker can say `qualified: classic`
  or another named template only once all its required cases pass. A three-call
  smoke test cannot certify every Werewolf role or Civ order type.

## Identity and frozen configuration

Key every result by exact provider model id (including suffix such as `:free`),
actual serving provider/endpoint, game/plugin version, template/role scope, and
configuration hash. Do not merge free/paid routes or model families. If routing
cannot be pinned or the serving provider is undisclosed, record that and label the
scope `automatic route`; do not claim a specific provider was tested.

Hash canonical sorted UTF-8 JSON containing: protocol/fixture versions and fixture
hashes, arena commit, game rules/prompt text and tool-schema hashes, prompt version,
model/provider routing and fallback policy, max input/output tokens, reasoning
effort, temperature/sampling options (including `provider_default`), timeout/retry
policy, repair version, memory, private-plan and thought-headline settings. Exclude
keys, account identifiers and volatile timestamps. Match the production request
builder, validation and accounting; do not build a simplified provider-only probe.

## Fixture construction and core cases

Fixtures have fixed seeds and role/seat assignments, minimal game-legal histories,
and fresh state for each case. Use player observations, never spectator state.
Constrain the legal target/action where necessary so success is objectively
checkable; do not grade whether the model adopts a preferred strategy. Freeze all
requests before the first call; retain failures and original attempts.

| Case | Required check | Real requests |
| --- | --- | --- |
| A | One offered tool; required ids/arguments valid; short nonempty `thought` when enabled | 1 |
| B | Rule-dependent action with constrained targets/resources, including correct seat identity | 1 |
| C | Representative longest fixture at the configured output/reasoning limit; action completes before cutoff | 1 |
| D | Game tool with no required game arguments, when supported; thought is still handled separately | 0-1 |
| E | Different phase or role using a different argument shape | 0-1 |
| F | Stateful continuation: apply a legal fixture action, then verify updated legal options/own plan only | 0-1 |

Thus 3-6 calls; declare applicable cases before execution. When a game has no
zero-argument action, D is `not applicable`, with the schema evidence, not a pass.
Never invent a no-op game tool just to meet this case. Every call records latency,
tokens, finish reason and raw-versus-eventual acceptance. Thought is a concise
decision explanation, not a test of private reasoning truthfulness or quality.

Truncation **resilience** is a separate free fault-injection test of the runner:
mock a length-limited response with no tool call, malformed arguments and optional
thought absent/present. Assert distinct error, bounded corrections, no invented
move and correctly marked fallback. A deliberately forced cutoff cannot fail a
model's normal core test. Case C detects cutoffs under the actual intended limit;
passing it cannot establish zero cutoff risk on longer real matches.

## Game coverage manifest

Generate required case names from the deployed plugin's tools and enabled role
handlers. Version the manifest; new roles/orders invalidate only affected scopes.

| Game | Minimum core fixtures | Extended checklist |
| --- | --- | --- |
| Liar's Deck | Legal owned-card play; call allowed only after an opponent play; near-limit history | Honest and bluff plays are both legal; 1-3 cards, jokers and enabled devil variant; first-turn call forbidden; empty hand/automatic call; table talk then action; hand resets and rising chamber risk |
| Poker | Legal check or call; constrained raise amount; near-limit betting history | Every deployed action (fold/check/call/raise/all-in/table talk), zero-argument shapes, min/max raise, short stack, all-in reopening/side-pot boundaries, no chips or hidden hole cards invented |
| Werewolf | Village speech/vote; wolf night choice; seer check; constrained witch action; near-limit day history (up to 6 by combining checks) | Every enabled role's active action at least once, including each night/death/first-night path; see list below |
| Civ | One `submit_orders` request with legal ids/resources; constrained movement/economy order; near-limit nation observation | Every deployed order type and refusal boundary, listed below; no full qualification before plugin/schema exists |

Werewolf classic coverage: villager discussion and vote; wolf private discussion
and victim selection; seer_check; witch_act with heal, poison and exhausted/no-use
potion branches; hunter death shot. Extended templates additionally enumerate every
registered active handler (e.g. Cupid distinct lovers, protection or special wolf
actions) from the deployed role registry, rather than guessing names. Passive-only
roles need observation/visibility and phase-transition fixtures, not invented tool
calls. Check self/dead/teammate target restrictions, null/abstain where legal,
simultaneous actions, private partner information and role-specific knowledge.
Uncovered action or branch stays unknown even if the core passed.

Civ coverage is provisional until the interface lands: movement/reachability,
settling/founding, building, training, combat orders when explicitly submitted,
research and diplomacy orders when implemented (offer/accept/reject, war/peace or
treaty actions). Derive exact names from the eventual `submit_orders` schema.
For each implemented type cover one accepted order and free validator negatives
for insufficient resources, stale ids, fogged targets and mutually conflicting
orders. Check one call per nation per round, batched orders, production/resource
accounting, victory progress and private plan off/on independently. Never mark
planned but unimplemented types as passed or silently omit them from the manifest.

## Decision rules

- **qualified** for the named scope: every required case completed a valid action
  on its first model response, without repair, fallback, truncation or rule error;
  expected thought contract passed; latency met the configured turn timeout.
- **unqualified** for that configuration: an explicit unsupported tool/parameter
  response, malformed/missing call, missing required thought, cutoff, invalid
  target/rule-dependent move or model turn timeout. Preserve the exact reason.
  A missing optional thought is a separate warning, not failure unless this test
  profile declares thought required. Qualification profiles must say which.
- **unknown**: not tested, incomplete coverage, changed hash, unavailable provider,
  429, network outage, 5xx or budget stop. These do not prove lack of tool ability.
  Report `unknown: rate limited` rather than hiding the cause behind a capability
  failure. Do not overwrite an earlier pass with an unrelated route's outage.

Production correction/retry behavior may still be measured, but an eventual repair
does not turn a first-response failure into a clean pass. Count all attempts and
costs. No automatic retesting until a pass; a retry of qualification needs a new
explicit click/approved job, linked to its failed predecessor. Existing historical
results remain inspectable. Show current runtime reliability beside qualification;
neither status substitutes for the other. Use a configurable initial freshness
limit of 7 days; expired results become unknown/current, retain last-tested status.

## Budget and user flow

Target under EUR0.01 per model per game's core click, often EUR0.002-0.01; this is
a target, not a fixed price or a cap exemption. Price the actual frozen fixtures
and model first. Reserve worst-case input plus configured output (reasoning
included) and all permitted transport attempts, with the arena's conservative FX
and unverified-model margin. Use the existing ledger to reserve/settle every call;
refused requests follow the existing audited zero-cost policy. Never read the key
in the browser, store it in results, or bypass the arena's money path.

Example only: 6 calls of 800 input/1500 output tokens at USD0.10/0.50 per million,
with EUR per USD conservatively 1, total at most EUR0.00498 before margins/retries.
This says nothing about the cost of stronger models, long prompts or full coverage.

Picker flow: `Test this model` -> review exact model/route, game/scope, call count,
settings and maximum EUR charge -> explicit confirm -> serial isolated calls ->
status and itemized results. Default per-click cap EUR0.01. If the reserved bound
does not fit, do not silently shrink the configured output limit; show the higher
bound and require the owner's explicit larger budget. Enforce the remaining
monthly EUR25 hard cap and usual EUR0.50 per-job/match ceiling; smaller click cap
wins. Recheck remaining allowance before each call, atomically reserve against
concurrent matches/tests. No background sweep or fleet testing from a single click.

This spec is not Nils' confirmation of a future click. UI wording should say
`core passed; night-role coverage incomplete`, not `all models work`. An unknown
or unqualified model stays deliberately selectable with the existing warning flow.

## Stored result and validation before implementation ships

Store authoritative results through the arena application database (new migration
owned by implementer); expose read-only result data to the picker and export JSON
under research for reproducibility. Do not change ratings, memories, match wins or
research outcomes. Fixtures cannot affect a running match or its RNG.

Required result fields: result id; UTC tested/start/finish timestamps; model id;
requested/actual provider; config hash and canonical configuration; protocol,
schema and fixture versions; game/template/role/action scope; status and reasons;
required/passed/missing cases; per case expected predicate, observed tool, schema
and game-validator result, thought present, finish reason, raw/repair/rejection/
fallback counts, latency, input/output/reasoning tokens, provider refusals, attempts
and ledger charge ids; total reserved/settled micro-EUR; parent retry id; expiry.
Export only redacted fixture data and bounded diagnostic excerpts, never keys,
headers, account data or unrelated live-match history.

Before paid use, free tests must verify identity/hash invalidation, unknown versus
failure classification, role/fog leaks, zero-argument tools with thought, cutoff
handling, status precedence, stale-result display, reservation races/caps, and
that bot/repair output cannot earn a pass. Run the deployed schema/validator on
each fixture. Then one separately approved inexpensive live click validates the
complete UI -> runner -> ledger -> result -> picker flow. Full role/order coverage
and strategic comparisons require separately priced, approved designs.
