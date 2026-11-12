# D-131 · Under the Werewolf circle: who claims what and who suspects whom, cut at the moment on screen

- **Date:** 2026-11-12
- **Decision:** Below the circle, a panel with two cards, side by side on wide screens and stacked on phones:
  - **"Who claims what":** each player who claimed a role, with the claims in order as chips, and what became of a claim in small words: "disproved: was Seer", "a lie", "true" (spectator only), "counter-claimed by …", "changed from …". Dead players are struck through.
  - **"Who suspects whom":** a grid of accuser (rows) by target (columns), shaded by accusing sentences and votes, with a dot (or the count) for votes. Self cells are hatched. "Most suspected" is named only when one player leads (no tie). Each cell has a tooltip with the counts.
  - **Moment:** both are cut at the moment on screen (a claim or an accusation shows from its `seq` on), live and in replays.
  - **Source:** the data is the match analytics (`claims`, `accusations`, docs/METRICS.md). The circle fetches it once with the game master's lines: once for a finished match, and for a running one again after new events, at most every 2.5 s.
  - **Spoiler-free:** the spoiler-free analytics carries only public facts, so "a lie" shows there only once a death revealed it, and "true" never.
  - **Heuristics:** a line under the panel says that claims and accusations are read from speech by simple rules, a guide and not proof.
- **Why:** Lead's Werewolf list (claims board, suspicion matrix). In the real 8-model match, the day turned on a Seer claim and its contradiction; the panel makes such turns visible at a glance, without reading every speech.
- **Alternatives:**
  - Arrows on the circle for speech accusations: with 8 to 13 seats they pile up on top of the vote arrows, and the grid stays readable at any size.
  - A separate tab: it hides the panel when it matters, during the day.
  - Showing heuristic readings as facts: rejected; they are marked as a guide.
