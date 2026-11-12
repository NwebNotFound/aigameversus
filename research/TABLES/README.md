# Explicit C1/W2 tables: reviewed client required before execution

One client, `arena.research.tables`, uses the existing research HTTP transport
and decision counter. It does not call providers, read keys or change arena money
code. CSVs enumerate every permissible table; JSON jobs pin their byte hashes.
The same canonical server batch id is used across restarts, directories and
attempts. There are no arbitrary model/setting/order overrides or rerun commands.

Lead approvals: C1 `454cd9d8` (four rotations with Haiku, EUR 1.00, supersedes the
earlier mistaken 16-match/Mistral description); W2 `5c29a3f0` (eight role cells,
EUR 3.50). Final ownership/order `44f4ab77`: #168 is the sole client, Researcher authors, Reviewer reviews,
C1 first smoke then W2, serial. These approvals do not replace the client's
money-path review/merge or the written PR pre-start report. No paid call was
made while writing this client. The older proposal documents' execution=false
means implementation/readiness gates remain, not an absence of these later
conditional scope/budget approvals. The JSON jobs record the latter explicitly.

C1 sets `match_budget_eur=0.20`. It must stop after table 1 for a Researcher
review: no failed agent, no model above 10% fallback, finished normally and
actual cost at most EUR 0.16. Later C1 tables and W2 require a persisted smoke
release linked to the finished report's SHA-256 and match id. W2 enforces 0.40
per match and reserves that same 0.40 per final Lead42080496 (supersedes 0.50).
The independent `spent + 3 * fresh estimate <= 90% of stage budget` and full
reservation rules must both pass before each start. No budget-blocked cell is
rerun. A pause, interruption, agent failure or above-gate fallback is a hold.

For unexpected-cost holds, freeze the following conservative operational rules:
fresh estimates must be below EUR 0.40 and at most 125% of their per-row saved
quote; actual costs above twice the start quote (bounded by the match cap) hold
the series. C1 table 1 uses its stricter EUR 0.16 threshold. Observations during
running matches use the same safety checks, so an early fallback can hold a game
even if its rate might later fall. The client attempts to pause only its own
running match on a safety hold; never resumes or aborts it automatically.

## Dry run (no match POST)

```bash
python -m arena.research.tables research/TABLES/C1.json
python -m arena.research.tables research/TABLES/W2.json
```

These modes only request free estimates, verify effective limits and save
dry-run.json. Live mode additionally requires `--execute`, `--review-evidence`,
`--pre-start-report` and `--arena-build`, each recording the actual reviewed
merge/report/build provenance. The client records these as operator-supplied
evidence, not a claim to have authenticated GitHub review or server build identity.
Researcher must verify them before invocation. Do not invoke live mode before
Reviewer approval and merge. No approval dialog or paid provider call exists in
dry-run mode. The API still enforces model-seat/confirm_spend/ledger guards.

The CLI journal lives in the OS user data directory under
`AIGameVersus/research-tables`, shared by every worktree. No output-directory
override can reset spending or an unresolved POST. C1 and W2 share one lock;
live API history is reloaded for the full batch (not the newest general page).
Server ledger costs, including failed starts that became matches, determine
cumulative spent, not a local successful-match summary. Unknown/duplicate batch
indices or a differing roster/settings/seed refuse further starts. The public
server API has no idempotency key, so the client fsyncs an intent before POST.
Any refusal or lost response retains that intent. On restart a single matching
server batch record is adopted; absent/ambiguous records hold for manual
reconciliation and are never automatically reposted. A crash leaves the lock
in place: verify the prior process is dead before removing that lock alone.
Never delete the stage journal to retry a refused request.

After a clean C1 smoke, Researcher writes `C1/smoke-release.json` in the journal:
`match_id`, `report_sha256` (digest of C1/001.json), and `evidence` linking the
written review decision. This checkpoint cannot clear a failed report: the
client rechecks its status/reasons/cost and re-observes server history. W2 cannot
start without it. A stage completion returns a summary, and every new finish
prints one status line for forwarding to Lead; the client sends no chat messages.

The lock coordinates this client on this host. It cannot atomically exclude
unrelated users/programs starting matches through the arena API; it checks the
live running list immediately before each POST. Existing server per-match/month
caps remain the authoritative financial boundary. No claim of distributed
exactly-once dispatch is made; ambiguous cases stop instead of risking duplicates.

Tests use a fake arena only. `mutations.json` records seven deliberate bypasses
(full reservation, 3x/90%, monthly hold, effective cap, dry-run dispatch, confirm_spend and unrelated-running-match exclusion) that made targeted tests
fail. Raw live exports remain local/ignored; no player observation is created
from the research CSV, which contains no hidden role map.

An active match has a persisted one-hour deadline; it cannot wait forever or
reset its timer on restart. Expiry holds and attempts to pause that own match.
C1 records the expected 120-event history window (W2 remains 40); verify the
actual deployed hook/build in the pre-start report before enabling execution.

Published C1/W2 JSON jobs are dry-run only: execution_plan_approved is false
and execution_approval_evidence is null. After the client review and Lead fresh
go, record that explicit execution decision before live mode. Earlier scope
approvals alone cannot start the client; fake tests use isolated approved copies.
