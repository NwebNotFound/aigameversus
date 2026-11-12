# D-134 · The post-match referee judges five moments chosen by rule with one Jev call, as unvalidated research tags

- **Date:** 2026-11-12
- **Decision:** Jev step 3 (`arena/jev/referee.py`, `POST` and `GET /matches/{id}/referee`).
  - **Moments:** a finished match with model seats gets at most one referee run. Its
    moments are chosen before anything is read. The model seats' moves are grouped as
    decision (a call, a vote, a bet, orders), talk (speech) and rejected (a refused
    attempt). Up to 5 are taken round-robin over these groups, the earliest first. Each
    group's available and chosen count is kept, and an empty group is named absent.
  - **Questions** (research/JEV/CALIBRATION.md), all in one Jev request:
    - per moment with a thought: does the move match the player's own reasoning (noul);
    - per talk moment: its perceived persuasiveness (score, the five rubric anchors);
    - per talk moment the engine's talk check (D-122) did not judge: the residual lie
      question (noul).
  - **State:** for each moment, only the events visible to that player before the move,
    its own thought and its own move.
  - **Money:** the call goes through `Budget.jev` under the match id, inside the match
    cap and the month cap. A cap stops it unsent (`failed`, `cap (...)`).
  - **Answers:** read strictly. A score must be a distribution over exactly the levels
    asked, else the run is `failed`, `bad_answer`.
  - **Tags:** stored per moment with the raw probabilities and `validated: false` (table
    `referee_runs`). GET answers only with `spoilers=true`. Nothing is written to the
    match or its log.
  - **Gates:** running it needs ARENA_ALLOW_JEV=1 (403) and confirm_spend (422). The flag
    stays off until Nils approves real Jev calls. Tests use FakeJev only.
- **Why:**
  - The protocol: one request per match, event-based selection with logged absent
    categories, no outcome-selected moments, only what the actor knew.
  - The deterministic talk check is the truth where it applies, so Jev only gets the
    residual lie cases.
  - The tags are AI grading AI (JEV-FINDINGS.md Q4): research data until people have
    labelled the same moments and the agreement passes the plan's publish rule.
- **Alternatives:**
  - The referee during a match: never; it must not touch a live match.
  - Choosing dramatic or decisive moments: outcome selection, which the plan forbids.
  - Sending the whole log: it would show other players' secrets.
  - Several calls per match: the plan caps it at one.
  - Showing the tags in the spoiler-free replay: they judge hidden play.
- **Not verified:** the exact field name of a score question's levels (`criteria`, as for
  the other types). JEV-FINDINGS.md says only "ordered array of descriptions". Check it
  before the first real call.
