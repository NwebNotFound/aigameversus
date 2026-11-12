# C1 call-configuration proposal

Decision source: Lead fcce19c0, 2026-11-12. Proposal only; no paid call approved.

Propose DeepSeek Flash output limit 4,000, reasoning effort low, tool choice
required. Preserve the already accepted reasoning option; increasing the output
allowance may leave room for the tool call after reasoning, but this is unproven.
Do not infer that omitting the reasoning option disables reasoning.

The existing model override is global, not game-scoped. Reviewer must establish
an isolated Civ configuration or explicitly document the wider scope before any
deployment. Freeze the effective options for every subsequent Civ pilot cell.

Free rotation-1 quote on the unchanged live configuration: EUR 0.073337, cap
EUR 0.20, fits. This is NOT a quote for the proposed 4,000-token configuration.
The estimator on merged client source 210d959 uses historical mean output, or
the global output limit without per-model call_options. Thus it cannot establish
the increased allowance's cost by itself. Reviewer has been asked to check current
main and obtain an appropriate adjusted-configuration quote. No paid test.

Future smoke requires D-137/D-138 deployed, actual rules_version/build/image and
options recorded, four fresh rotation quotes each at most EUR 0.20 and a new Lead
go. Retain the EUR 0.16 smoke cost stop, failure/fallback/history-cut gates and
EUR 1.00 cumulative C1 ceiling, including EUR 0.011856 already spent. If options
are explicitly unsupported, propose and quote a replacement before changing the
roster. No replacement is needed solely from the current cutoff evidence.

W2 requires a reviewed C1 outcome, not a clean C1 smoke. The aborted pre-rules
outcome has been reviewed by Lead; W2 still needs its separate execution go.
