# D-066 · Werewolf role selection in the new-match form

- **Date:** 2026-11-11
- **Decision:**
  - The form shows the templates for the chosen table size
    (`GET /games/werewolf/templates?players=N`, which gives each template's
    roles at that size, or none when it does not fit). A template that needs
    more players is listed but disabled. Choosing one fills the checklist; a
    template in use follows the player count.
  - Changing a count makes the mix "Custom". The checklist is grouped by team;
    a unique role is a checkbox, any other role a count. Villagers are not
    chosen: they fill the free seats and their number is shown.
  - The web server checks a custom mix a quarter second after each change
    (`/matches/new/werewolf`, which forwards to the arena's selection check)
    and shows its balance light (green when even, amber when it favours one
    side) and its problems: next to the role when the problem names one, above
    the checklist otherwise. On submit the same check runs again before the
    match starts, so a mix that cannot be played is refused at its fields with
    the counts kept.
  - A template goes to the match as `settings.template`, a custom mix as
    `settings.roles` (counts above 0). The random template shows no checklist:
    its roles come from the match seed.
- **Why:** The selection rules and balance stay in `games/werewolf/selection.py`;
  the form only shows what the arena says, so the two cannot disagree.
- **Alternatives:** checking the rules in the browser; a villager count to set
  by hand; a red light for imbalance (the arena has three verdicts, not a scale).
