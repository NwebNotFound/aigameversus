# D-055 · Werewolf statistics: definitions

- **Date:** 2026-11-11
- **Decision:** `arena/stats/werewolf.py` counts per player and match: vote
  accuracy (of the votes for a player cast while on the village side, the
  share that hit a wolf; abstentions are counted separately and wolves' own
  votes are left out), rounds alive (a round is a night and the day after it;
  a player who dies in round `n` was alive for `n` rounds, a survivor for all
  rounds), wins (from `game_over`), and for the seer the rounds she lived and
  whether she died. The wolf side is the pack from `pack_revealed` plus
  `joined_pack` and `infected` players, from the moment they join.
- **Why:** The spec names "vote accuracy, survival, seer outing speed" without
  formulas. Everything comes from events the plugin already emits (the
  spectator log has all roles). "Outing speed" is measured as how long the seer
  lives, since the log has no event for a claim.
- **Alternatives:** counting wolves' votes too (a hit means the opposite for
  them); measuring the outing by chat text (the log has no claim event).
