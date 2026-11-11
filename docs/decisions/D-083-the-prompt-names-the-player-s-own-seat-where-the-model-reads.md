# D-083 · The prompt names the player's own seat where the model reads it

- **Date:** 2026-11-11
- **Decision:** Besides the first line of the system message, the prompt now
  says once more that every mention of the seat is the player, ends the ask
  with "You are p8.", and starts every event line that the player did (its
  `player`, `caller` or `from` is the reader) with `[you]`. Events that only name the reader in
  another field (a vote against them) are not marked: the player did not do
  them. Other players' words stay as they were written.
- **Why:** In the first real Werewolf match the seer (seat p8) wrote about
  "p7 and p8" as if they were others, attacked its own seer claim in public
  and tried to vote for itself; another model called its own seat suspicious
  in its thought. Both had read their seat once, at the top of a long
  prompt, and then met it many times as a plain id among other ids.
- **Alternatives:** Names instead of seat ids (needs player info in every
  game's events, planned for the UI); rewriting other players' words to say
  "you" (would change what was said); marking every event that names the
  reader anywhere (marks votes against the player as theirs).
