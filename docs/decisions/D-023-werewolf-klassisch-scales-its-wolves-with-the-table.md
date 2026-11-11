# D-023 · Werewolf "Klassisch" scales its wolves with the table

- **Date:** 2026-11-11
- **Decision:** The Klassisch template has `by_players`, a per-size table in
  `games/werewolf/templates.yaml` that overrides the werewolf count: 2 wolves
  for 6-8 players, 3 for 9-15, 4 for 16. Seer, witch and hunter stay one each;
  villagers fill the rest. `apply_template` reads the table; there is no wolf
  formula in code.
- **Why:** The balance light (D-022) must not favour the village. With the
  fixed roles the total is `11 + players - 7 * wolves`: +3, +4, +5 for 6-8
  players, -1, 0, +1 for 9-11, +2 to +5 for 12-15 and -1 for 16. The light is
  *even* at every size from 6 to 16. 6-8 players cannot get closer to 0 (3 of
  6 is not allowed, 3 of 7-8 is a large share of a small table). Wolves stay
  under half the players everywhere. A test checks every size.
- **Alternatives:** `max(2, players // 4)` wolves, i.e. 2 wolves up to 11
  players (rejected: leaves 9-11 players village-favoured at +6 to +8); a
  formula field in the template format.
