# D-069 · The Werewolf circle draws votes from the log and shows no model names

- **Date:** 2026-11-11
- **Decision:** The Werewolf circle (`layout: player_circle`) gets its vote arrows
  from the match log, not from the plugin: the votes cast since the day began
  (the last one per voter, an abstention takes a vote back) stay drawn after the
  result until the next night starts, with the count against each player on
  their seat. The backdrop follows the plugin phase: night, dusk or day. Roles
  show only with spoilers on, as a `?` otherwise. Seats show the player id, not
  a model name, because the spectator spec has none.
- **Why:** The votes are public events, so the log is the source and the plugin
  needs no UI state. The spec carries seats and phase only.
- **Alternatives:** adding the votes to `render_spec`; passing the model names to
  the board (needs the match record in the board props, a later step).
