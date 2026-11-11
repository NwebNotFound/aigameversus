# D-022 · Werewolf role selection: wolf count and balance light

- **Date:** 2026-11-11
- **Decision:** For the selection rules ("at least 1 wolf", "wolves fewer
  than half the players") the White Werewolf (team `solo`) counts as a wolf,
  like the roles of team `wolves`, because it hunts with them. The balance light sums `weight × count`
  over the filled selection: above +5 is *village*, below −5 is *wolves*,
  anything from −5 to +5 is *even*, i.e. less than one werewolf's weight (−6)
  away from 0. "Zufällig ausgewogen" draws 300 random playable mixes from the
  match seed (wolf count, special roles on both sides, villagers for the rest)
  and keeps the first one closest to the template's `target_balance`. Problems
  carry a stable `code` and the role id, so the UI can translate the English
  message.
- **Why:** A fixed margin tied to the strongest repeatable role is easy to
  explain next to the light; counting the White Werewolf keeps 3 wolves plus it
  from passing as "3 wolves".
- **Alternatives:** a margin scaled by player count; counting only team
  `wolves`; picking the random mix by search instead of sampling.
