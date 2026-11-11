# D-012 · One engine loop for all turn modes, one action per request

- **Date:** 2026-11-11
- **Decision:** The loop is the same for `sequential`, `simultaneous` and
  `tick`: ask all active players at once, apply their actions together, then
  `step`. Sequential games may name at most one active player; tick games may
  name none. An agent returns one action per request; a turn with several
  actions (talk, then play) is the plugin keeping the player active. The engine
  is async. A turn that produces no game event stops the match as a plugin bug.
- **Why:** One code path to test. Async lets simultaneous players call their
  models in parallel later, while the log order stays the seat order.
- **Alternatives:** A loop per turn mode; batches of actions per request (may
  come with the agent runner if model calls need it).
