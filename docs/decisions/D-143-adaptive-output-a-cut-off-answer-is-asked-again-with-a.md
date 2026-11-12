# D-143 · Adaptive output: a cut-off answer is asked again with a larger output limit

- **Date:** 2026-11-12
- **Decision:** The engine setting `adaptive_output`, `"off"` (the default) or
  `"on"`. With it on, an answer cut off at the output limit (`finish_reason`
  length) that holds no usable tool call is asked again: the same prompt and
  tools, with twice the output limit. This repeats until it finishes or the
  model's ceiling is reached (`limits.output_ceiling` 8000, or the model's own
  `output_ceiling`; never below its start), for example 1500, 3000, 6000, 8000.
  - The reasoning effort stays as it is.
  - A cut-off answer that still holds a usable call is not asked again.
  - What is still unusable at the ceiling goes to the engine's corrections as
    before.
  - Every call goes through the `Budget` and is booked at its own, raised
    output limit (at most the ceiling): the most that call can cost. So a raise
    that would pass a cap pauses the match before it is sent.
  - The `decision` event gets `output_limits` (the limits of each answer, for
    example `[[1500, 3000]]`) only when a raise happened. The tokens of every
    call count in the answer's numbers.
  - The estimate keeps the expected cost as it was and adds
    `worst_case_micro_eur`: every answer at every limit of the chain, each call
    with its whole prompt.
  - **Time:** a seat with the setting on gets its turn timeout once per call of
    its chain (`ModelAgent.turn_time_factor`, 4 for 1500 to 8000). Without that,
    the raised calls, the longest and dearest, would be the ones the turn's 60 s
    cut off after they were booked. A call that still runs out of time is cancelled:
    its booking stays (the provider may bill it), the turn is a random move with
    reason `timeout`, and nothing is booked past the cap.
  - **History:** the ledger's mean output per model (`Ledger.output_tokens`) counts
    calls, not answers. In a match with raises, a cut-off 1500 call and its 3000
    retry count as two answers of 2250, so a later estimate under-reads such a
    model. For a match with the setting on, read `worst_case_micro_eur`, and
    `worst_case_fits` (the worst case within the match cap and the month left).
  - Like `answer_repair` it is the engine's setting: the game never sees it,
    and `match_started` records it.
- **Why:** Nils wants a model to be able to finish its sentence. A cut-off
  answer today costs a correction with a shorter answer, or a random move: the
  first Civ smoke lost two of three DeepSeek turns that way. Doubling finds a
  fitting limit in a few steps without paying the ceiling on every call, and
  booking each call at its own limit keeps the caps exact.
- **Alternatives:** Always send the ceiling (every call books and may cost the
  most). Raise the limit for the rest of the match after one cut-off (helps the
  next turn, not this one). Lower the reasoning effort on a cut-off (changes how
  the model plays, so not without the provider needing it).
