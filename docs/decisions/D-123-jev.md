# D-123 · Jev calibration preserves intent and separates human agreement from ground truth

- **Date:** 2026-11-12
- **Decision:** Step 4 is a proposed calibration/agreement study under research/JEV, with fake clients only until Nils explicitly approves real decision calls. Use dual independent human labels, blocked development/holdout splits, threshold on top probability and a 95% precision target with uncertainty. Ambiguous intent and invented amounts cannot become repaired strategy. Referee tags require human agreement and remain research data. Repair-OFF sensitivity drops whole affected matches; causal effects require actual separately approved paired games. Fewer than 100 independently eligible blocks, unavailable human raters/adjudicator, or an unfrozen registration block execution; nothing is spent.
- **Why:** API concentration is not demonstrated correctness; sparse labels and repaired outcomes cannot establish intent preservation or a counterfactual Elo. The study must make abstention, failures, sampling and uncertainty visible before enabling a paid repair tier.
- **Alternatives:** use the confidence field or 20 labels as sufficient calibration (overstates evidence); let Jev infer a strategically sensible move (violates the boundary); remove repaired moves and reuse unchanged match outcomes as OFF results (invalid counterfactual); treat AI referee tags as ground truth (unvalidated).

## Registration freeze (blocking, pending merge)

The registration merge commit is **pending**; this draft is not a completed
registration. After Reviewer merges #138, Researcher records that exact merge SHA
here and in PLAN.yaml in a dated registration note before any labels/predictions
are collected. That SHA identifies the immutable design text and CI tests; the
later note records it without pretending a commit can contain its own future SHA.
The corpus manifest, split and configuration hashes are frozen alongside it.
Subsequent changes require dated amendments with reason, prior/new hashes and
whether any labels or predictions were seen. No tuning on a reused holdout.
Until that note exists, `registration.state` stays `pending_merge_freeze`.
