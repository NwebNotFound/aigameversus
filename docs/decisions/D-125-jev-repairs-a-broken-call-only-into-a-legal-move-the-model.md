# D-125 · Jev repairs a broken call only into a legal move the model meant, above a threshold, never otherwise

- **Date:** 2026-11-12
- **Decision:** `answer_repair` takes `"v2"`: everything of `"v1"`, plus a tier between the
  last refused correction and the random fallback. A move refused for its answer (not for
  a timeout or a failed agent) goes to a `Repairer` (`arena/jev/repair.py`, Jev's `choice`
  question). The engine draws the game's own random legal moves on a stream of their own
  (`"repair"`, so the game's randomness is untouched), checks each, and offers only those;
  speech tools are never options and optional free text is dropped; a bounded integer (a
  bet) is offered as its minimum, middle, maximum and the amount the model tried. Jev reads
  the player's own observation or summary, the tail of its own reasoning and its refused
  calls, nothing else. Its pick plays only when its top probability (not Jev's
  `confidence`, which depends on the number of options) reaches the threshold for that
  many options (`config/jev.yaml`, 0.90 everywhere until calibrated); the pick is checked
  again and marked (`action_accepted.repaired_by: "jev"`, `top_probability`; the move's
  `decision.jev` holds the verdict either way). Anything else, including every error of
  the alpha API, leaves the random fallback, which stays. Each call is booked in the
  ledger before it is sent (request bytes at `input_usd_per_mtok`), settled at Jev's
  `usage.cost`, and counts against the match and month caps. No call is sent unless the
  server runs with `ARENA_ALLOW_JEV=1`, and `POST /matches` refuses `"v2"` otherwise.
- **Why:** Nils' principle: Jev never decides a move of its own, never picks models, has no
  seat. Offering only checked legal moves, and only when the model's call was already
  refused, keeps it a translator of the model's intent. Thresholding on the top
  probability makes the bar the same for two options and for sixteen (the findings'
  table). Candidates from the game's `random_action` need no new plugin method and are
  legal by construction. The refused attempts stay in the log, so the tool-error count
  of a model does not change; the report counts repairs per tier and player.
- **Alternatives:** Jev before the corrections (would hide the model's own retry); Jev
  free to name any move (could play a move nobody meant); a threshold on `confidence`
  (lower bar for more options); a new `legal_actions()` in the plugin interface (every
  game to change, and endless for bets); a constrained chat model (the findings prefer Jev).
