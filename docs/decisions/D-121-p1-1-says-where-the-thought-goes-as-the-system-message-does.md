# D-121 · p1.1 says where the thought goes as the system message does; p1 stays the baseline

- **Date:** 2026-11-12
- **Decision:** The p1 rules of Liar's Deck, Poker and Werewolf say "Your
  private thoughts are the plain text of your answer", while the system
  message of every game asks for the thought inside the tool call and
  nothing outside it. A new prompt version `<game>-p1.1` is p1 with exactly
  that sentence replaced ("Your private thoughts go in the `thought`
  argument of your tool call"), built from p1 by
  `with_thought_in_the_call` (`arena/agents/prompt.py`) and without a
  summary, like p1. p1 stays word for word as it was: the default and the
  baseline of the experiments already run. p2 and p3 never had the sentence.
- **Why:** Two instructions that disagree can make a model write long text
  outside the call, which then runs into the output limit (the audit of
  be2f808a: 12 of 13 refusals were cut off). Whether that is the cause is
  for a paired comparison to show; changing p1 itself would break every
  comparison with the matches already played.
- **Alternatives:** Editing p1 (silently changes the baseline); dropping the
  sentence from the system message instead (most calls rely on the thought
  in the call); a p1.1 file per game (three copies of the rules to keep in
  step).
