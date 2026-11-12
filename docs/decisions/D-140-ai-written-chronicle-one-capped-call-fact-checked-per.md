# D-140 · AI-written chronicle: one capped call, fact-checked per chapter, cached

- **Date:** 2026-11-12
- **Decision:** `POST /matches/{id}/chronicle/ai {style, lang, model, confirm_spend}` has a model
  retell the template chronicle of a finished match (`arena/chronicle/ai.py`).
  - **The call:** one call with the template chapters as JSON and one tool, `write_chronicle`
    (one text per chapter number).
  - **The facts:** the template stays the source of the facts. Each rewritten chapter is
    checked against its own template text. It may add no player name, no digit, no number
    word, and no card or role word (English and German lists; the role words come from
    `games/werewolf/roles`). It may be at most 3× the length of its template. It may not be
    empty.
  - **A failed check:** the chapter keeps its template text, and `checks` says why.
  - **The label:** the answer says `ai_written: true`, a label ("AI-written retelling,
    fact-checked against the match log"), the model and `prompt_version` (`chronicle-ai-1`).
  - **The cache:** the table `ai_chronicles` caches the result per (match, style, language,
    model). A second POST and `GET /matches/{id}/chronicle/ai` serve it and spend nothing.
    One request writes a chronicle at a time: a running row answers 409. A failed row may be
    tried again.
  - **Money:**
    - The same guards as a paid match: `ARENA_ALLOW_MODEL_SEATS` (403), `confirm_spend`
      (422), the key (503) and a durable ledger (503).
    - The call is booked in `model_calls` under its own id, `uuid5("chronicle/<match>/<style>/<lang>/<model>")`.
      The cap is EUR 0.03 for that id (`Budget(match_eur=0.03)`), so every retry of one
      chronicle shares the same 0.03.
    - A request whose worst case (request bytes and the output limit, as the budget books
      it) is above 0.03 is refused (422) before anything is booked.
- **Why:** Lead's task (Nils said yes). The chronicle must be "AI-written" and labelled, true to
  the log, paid once per match/style/language, and at most EUR 0.03 each.
  - Rewriting the checked template, rather than telling the model the raw log, keeps the
    facts in one place that is already tested. The model never sees hidden information beyond
    what the template chronicle already shows spectators.
  - A word-level check is crude, but it is deterministic and free. It errs towards the
    template: a chapter that fails falls back, and the chronicle is never wrong.
- **Alternatives:**
  - A second model call to judge the facts: it costs money and is not deterministic.
  - The raw event log as the prompt: more facts to invent from, and a larger request.
  - A cap per match rather than per chronicle: four styles × two languages could then spend
    the match's whole 0.50.
  - A UI button: left for a follow-up. The first samples come from the API, after Lead's go.
