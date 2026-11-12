# D-132 · A model is qualified per configuration by its first answers to real turns of seeded bot matches

- **Date:** 2026-11-12
- **Decision:** The core pre-flight of research/QUALIFY.md runs in the arena
  (`arena/qualify/`, `POST /qualifications`).
  - **Fixtures:** each case's fixture is one real turn request of p1, captured from a
    random-bot match with a fixed seed: the first fitting turn, or for case C the
    turn with the most history over the search seeds. The model is offered only the
    case's tools and never speech. The game state of that turn is kept to judge the
    answer and is never sent.
  - **Judging:** the answer goes through the production `ModelAgent` and is judged by
    the engine's own check (offered tool, schema, `plugin.validate`). Only the first
    model response counts and no correction is asked. Each case records whether its
    thought is required (case A) or optional (a warning only).
  - **Verdict:** unqualified beats unknown, and unknown beats qualified. Only an explicit
    refusal of the frozen configuration (UnsupportedParamsError) fails a case. A
    generic 400, a 429, a 5xx, an outage, a too-long prompt or a budget stop leaves it
    unknown, with its reason. "repaired (v1)" is a badge on a qualified v1 job.
  - **Configuration hash:** results are keyed by a hash of the configuration. It
    covers the protocol and manifest versions, the fixtures, the exact requests sent,
    the model and route, the call options, answer_repair, thought_headline, memory off
    and private plan off. The current status of a configuration is its newest decisive
    result, for 7 days from that result's own finish. A later unknown shows as the
    latest attempt and never refreshes it.
  - **Money:** a job has the guards of a paid match: ARENA_ALLOW_MODEL_SEATS,
    confirm_spend, the key and a durable ledger. It books under its own id against
    the smaller of the click cap (default 0.01 EUR) and the per-match cap. It is
    refused when its worst case (every case's booking bound × 4 transport tries)
    does not fit. The Researcher's decision: keep the production retries and the EUR 0.01
    default. A larger max_eur is the owner's explicit choice per click, at most EUR 0.50.
    One job runs at a time, and a restart leaves a running job unknown.
  - **Games:** Liar's Deck and Poker have core manifests. Werewolf and Civ follow
    once their case lists are written.
- **Why:** QUALIFY.md's rules:
  - real requests through the production path, from deterministic fixtures, never
    spectator state;
  - first response only;
  - the money path of a match.

  A bot match with a seed needs no hand-written game states and no change to the
  plugin interface. Every game gets fixtures the same way, and a change of a game
  changes their hash.
- **Alternatives:**
  - Hand-written fixture states: per game, and they drift from the rules.
  - A provider-only probe: the protocol forbids it.
  - Grading the eventual answer after corrections: forbidden, it would hide
    first-response failures.
  - Shrinking the output limit to fit the click cap: forbidden; the job is refused
    and the cap must be raised instead.
