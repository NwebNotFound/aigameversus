# D-045 · Turn limits of Poker and Liar's Deck are upper bounds from the rules

- **Date:** 2026-11-11
- **Decision:** Each game's `max_turns` (D-040) is what its rules allow at most,
  computed, not guessed. **Liar's Deck:** every round ends with at least one
  trigger pull and a revolver has 6 chambers, so at most players × chambers
  rounds; a round has at most one play per dealt card plus the call; every
  action may carry one `table_talk` turn: 4 × 6 × 21 × 2 = 1,008.
  **Poker:** `turn_bound()` sums over the hands: 4 streets × players, plus at
  most (players − 1) more actions per raise; a full raise lifts the bet by at
  least the big blind, so a hand holds at most all chips ÷ big blind full raises
  plus one short all-in per player; each action may carry one `table_talk`
  turn. With the defaults and 6 players that is 70,400. Settings whose bound is
  higher (bigger stacks, more hands, smaller blinds) are refused.
- **Why:** A bound from the rules can never stop a legal match, and still stops
  a looping one.
- **Alternatives:** a measured maximum with a safety factor; one large limit for
  every game; letting the bound grow with the settings by overriding
  `Match(max_turns=...)` per match.
