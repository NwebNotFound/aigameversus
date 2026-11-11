# D-047 · Werewolf day: captain, narrator and language

- **Date:** 2026-11-11
- **Decision:**
  - The captain is elected at the start of day 1, before the discussion,
    when `captain` is on (default from `options.yaml`). Every living player
    votes once in seat order; most votes win, a tie is broken by the match
    seed. The captain's day vote counts `vote_weight` (2). A dying captain
    names a living successor right away (after the Hunter's shot if the
    captain is the Hunter). There is no new election later.
  - The narrator is template text in the match `language` (`de` default per
    D-001, or `en`): a public `narration` event with `key`, the facts and the
    `text`, at nightfall, each morning, the captain's election and handover,
    each vote result and the end. `arena/gamemaster/narrator.py` can retell a
    narration with any `ModelCall` (style plain, epic, news or sports, at most
    60 words); on a model error, an empty or an overlong answer the template
    text stands. Facts go into the prompt as escaped JSON data. Nothing calls
    it yet; the match runner (step 1.6) decides where narration is retold.
- **Why:** The plugin never calls a model (rule 6), but the log always has a
  readable narrator line, and a model can only add colour, never change facts.
- **Alternatives:** captain elected after the first discussion; a new
  election when the captain dies without successor; the narrator inside the
  plugin with a model call.
