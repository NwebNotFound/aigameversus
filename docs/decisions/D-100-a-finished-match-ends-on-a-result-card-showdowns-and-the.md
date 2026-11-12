# D-100 · A finished match ends on a result card; showdowns and the final ranking are structured

- **Date:** 2026-11-11
- **Decision:** When a match is over and its end is on screen, a result card
  covers the stage until the viewer closes it ("Show the board"). This means
  the last step of a replay, or a live match that has finished. The headline
  is the transcript's own line about the end (`game_over` or `match_over`). A
  game whose end names a winning side, such as Werewolf's `game_over` with
  `winner` and `winners`, shows that side large and everyone else small.
  Every other game shows a podium of the first three ranks (shared ranks side
  by side), with the rest in a list. The ranks come from the match's
  placements. In the commentary, the `match_finished` line becomes a ranked
  list. A `showdown` line becomes a row per hand: avatar, cards, the hand's
  kind and the chips it won from the pot lines that follow. The caption above
  the timeline wraps instead of being cut off, and it never shows the ranking
  line.
- **Why:** Reviewer's viewer check found the end of a match read as a run-on
  paragraph cut off with an ellipsis, and showdowns as a wall of text. The
  data is all in the transcript lines (`raw`) and the match record, so the
  web adds no new wording: names, hands and amounts come from there.
- **Alternatives:** A results page apart from the replay (the viewer leaves
  the board at the climax); asking the transcript for a result sentence per
  game (still a paragraph).
