# D-128 · The Throne of Tokens scoreboard is public by rule; positions and contents stay fogged

- **Date:** 2026-11-12
- **Decision:** Public to every nation: the total number of cities in the
  world, each nation's city count, the cities a domination needs, who holds
  the gold countdown and how far it is (not its gold), reputations, treaties
  and wars. Private: other nations' round-limit scores and stocks (a score
  holds gold and population), where cities and armies are, what cities
  hold, and armies outside a nation's own sight. The observation carries the
  public part as `scoreboard` (docs/civ-interfaces.md), built by the plugin
  from the state, so nothing reaches a nation through a number computed from
  fogged objects. Decided by the lead after the review of #119.
- **Why:** DESIGN.md makes domination "50 % of all cities" and the economic
  countdown visible to all, and a player can only play for a threshold it
  knows. Counts say who is ahead without saying where to strike.
- **Alternatives:** Only the nation's own share (it could not tell how close
  a rival is to winning); everything fogged including counts (no way to see
  a domination coming, which the countdown rule is meant to allow).
