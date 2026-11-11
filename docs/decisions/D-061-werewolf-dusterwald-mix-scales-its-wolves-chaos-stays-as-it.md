# D-061 · Werewolf "Düsterwald-Mix" scales its wolves; "Chaos" stays as it is

- **Date:** 2026-11-11
- **Decision:** Düsterwald-Mix has a per-size `by_players` table for its werewolf
  count (as Klassisch, D-023): 2 wolves for 8 players, 3 for 9, 4 for 10-16.
  With its six special roles (seer, witch, hunter, Cupid, Bear Tamer, Little
  Girl) the total is `15 + players - 7 * wolves`: +9 at 8 players, then +3, -3,
  -2, -1, 0, +1, +2, +3 for 9 to 16. The light is *even* at 9-16 and within
  -1..1 for 12-14. At 8 players it stays *village* (+9): a third wolf does not
  fit beside six special roles (nine roles for eight seats), so +9 is the
  nearest reachable value. Chaos is unchanged: its 12 non-werewolf roles
  (Prime Wolf and White Wolf among them) and 2 werewolves give `players - 7 *
  wolves`, which is 0, +1 and +2 for its 14, 15 and 16 players. Tests pin the
  totals of both templates at every size.
- **Why:** Fixed 2 wolves left Düsterwald village-favoured everywhere (+9 to
  +17). The table follows the same idea as D-023: wolves grow with the table
  and the light is read from the weights.
- **Alternatives:** dropping a special role from the 8-player mix to allow a
  third wolf (changes the template's roles, not only its counts); a formula
  field in the template format.
