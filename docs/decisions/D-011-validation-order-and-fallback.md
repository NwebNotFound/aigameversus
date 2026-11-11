# D-011 · Validation order and fallback

- **Date:** 2026-11-11
- **Decision:** The engine checks an action in three steps: the tool is offered
  now, the arguments match the tool's JSON Schema (`jsonschema`), the plugin's
  `validate` accepts it. A rejected action is returned with the error; after 2
  corrections the game's `random_action` plays instead and the log marks it
  with `action_fallback`. Every attempt is logged, visible only to that player
  and to spectators.
- **Why:** Generic checks give every game the same clear errors for malformed
  model output, and plugins validate only rules. A random legal move keeps the
  match going in every game without a per-game notion of "do nothing".
- **Alternatives:** A per-game default action; skipping the player's turn.
