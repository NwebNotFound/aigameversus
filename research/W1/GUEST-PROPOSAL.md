# W2 strong Werewolf guests: reduced pilot proposal

The overnight allocation is EUR 3.50; the exact plan still needs Lead acceptance.
No paid call is made by this proposal. Llama and Qwen remain excluded from the
hosts after W1 reliability failures; do not retune them inside this experiment.

Free current-stack estimates for one guest plus seven host seats:

| Guest | Exact OpenRouter id | Estimate per match |
| --- | --- | ---: |
| GPT Terra | openai/gpt-6.1-terra | EUR 0.136646 |
| Claude Sonnet | anthropic/claude-sonnet-5.5 | EUR 0.241947 |
| Kimi | moonshotai/kimi-k3.1-pro | EUR 0.241947 |
| Gemini Carbon | google/gemini-4-carbon | EUR 0.241947 |

Quotes are guides, not spending bounds. All four appear in the fresh catalog;
their declared tool compatibility does not constitute an empirical pass. The
catalog marks their arena reliability unknown (zero prior moves).

The earlier 32-match full-rotation sketch would estimate EUR 10.611368, exceeding
this allocation. This proposal instead fixes eight cells: every guest plays one
wolf and one seer, at the same seed/seat and with the same seven host entries as
the other guests. Estimate: EUR 1.724974 before actual variation; the EUR 3.50
ceiling remains hard. All four get a wolf cell before anyone gets a second cell;
within-block guest order is fixed by seed 2026111205 before observing outputs.
Budget stopping may leave a partial second block; that is reported, not filled
by extra spend or outcome-selected reruns.

The fixed game seed 2103001 was chosen before the free in-process random-bot
fixture was played. That fixture yields p3=seer and p4=werewolf; all roles are
pinned in the YAML and tested without an API/model client. Role-map knowledge is
for schedule construction only and never added to player observations. Other
roles and games remain later work; two cells do not demonstrate full qualification.

The five unique hosts are GLM, DeepSeek, GPT Luna, Mistral and Haiku. GPT/Haiku
each occupy two seats. Freeze p2, memory off, repair off, low effort and the actual
production 1,500-token/60-second defaults before any model call. If a provider
refuses these settings, record that failure and hold; no automatic tuning or
replacement. These are configuration-specific observations, not family rankings.

Before each POST /matches, read the real ledger and effective match cap. Require
both `spent + 3 * fresh estimate <= 0.9 * 3.50` and `spent + full enforced cap <=
3.50`, one match at a time. The server's cap remains EUR 0.50, monthly EUR 25;
notify/hold at EUR 20 spent. No retries of failed matches. A failed agent, failed
or interrupted match, or guest fallback share above 10% holds the series for Lead.
Do not call a two-cell model "qualified" even if there are no observed failures.

[YAML](../../experiments/W2_werewolf_guests.yaml) and the explicit CSV are a
proposed study schema, not input accepted by the existing E1 experiment runner.
An explicit-CSV API client must be implemented/reviewed before spending. It must
match the frozen roster/seed/settings, account every attempt against the shared
stage allowance and retain missing/failed cells. An import error must never fall
back to an unvalidated live request. This proposal does not authorize that client
to spend before Lead accepts the exact plan.

The client must whitelist POST body fields rather than forwarding this whole
YAML: only game, models, seed, game settings, memory and batch metadata go to the
arena. Never copy expected_roles or the full schedule into a player observation.
Ledger totals are cumulative across attempts/restarts under the same overnight
guest allocation; a new output folder cannot reset the EUR 3.50 allowance.

Amendment before execution, Lead instruction `11df3917`: p2 replaces the earlier
proposed p3. All eight guest/seat tables were estimated for free again; both seat
placements have the displayed per-guest quote, strictly below EUR 0.40. Saved
responses and current catalog entries are in guest-preflight.json. The catalog
is the tool-compatible picker catalog; declared compatibility remains untested.
Configured hosts must be sent by catalog alias (for example gpt-luna), with exact
provider ids retained as metadata; the API rejects their provider ids as aliases.

No start until #144 is merged on main AND deployed in a Reviewer-verified rebuild.
Then verify `settings.match_budget_eur` is enforced, record its value, re-estimate
every table under the final settings, and send Lead a one-line pre-start report.
The earlier cap-lowering alternative is superseded by this explicit #144 gate.
Until a lower per-match value is chosen and verified, reserve the full EUR 0.50;
do not assume an estimate is an enforceable spending limit. This remains a plan
only, with execution approval false and no live client or paid request launched.
