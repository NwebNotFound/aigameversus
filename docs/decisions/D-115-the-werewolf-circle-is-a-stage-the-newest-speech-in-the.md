# D-115 · The Werewolf circle is a stage: the newest speech in the middle, deaths turn the role over

- **Date:** 2026-11-12
- **Decision:** The Werewolf circle stages the scene:
  - The newest speech (or pack whisper, spectators only) stands in the middle of the circle as a bubble with the speaker's avatar and name. A dashed tail runs to the speaker's seat, which glows. The bubble shows five lines and fades out; the commentary keeps the whole speech.
  - A new phase, a vote result or a death ends the scene and clears the stage.
  - While votes are cast, a tally of the day sits under the bubble, most votes first; the leader is outlined.
  - A dead seat turns its card over to the role the game announced in `player_died` and says how the player died ("killed at night", "executed"). That role is public, so it shows in the spoiler-free view too; living players stay "?".
  - The phase moves to a corner pill while the stage is in use.
  - On the ring, names drop their "(model)" suffix: the line under the name and the cast bar already show the model, and narrow circles hide that line.
  - Motion (bubble rise, card turn, phase move) is off with reduced motion.
- **Why:** Nils wants Werewolf to be top priority and awesome to watch. In the audit, the circle never said who was speaking (the words were in a box below the board), a death left only an X, and at 375 px the long names ran off the circle.
- **Alternatives:** Bubbles next to each seat. They overlap at 8 to 13 seats and on phones, so one stage in the middle with a tail scales to any table. Keeping dead roles hidden in the spoiler-free view would hide what every player at the table was told.
