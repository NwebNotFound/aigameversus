# D-009 · Plugins change state only through events

- **Date:** 2026-11-11
- **Decision:** The plugin interface differs from the sketch in the spec.
  `setup`, `apply_actions` and `step` get a context and call `ctx.emit(...)`
  instead of returning events; the engine passes every emitted event to a new
  method `apply_event`, the only place where a plugin may mutate its state.
  `initial_state` (pure, no randomness) replaces the state-building half of the
  spec's `setup`. `validate` returns `None` or an error message. `random_action`
  is part of the interface. `render_spec` is left out until the UI defines what
  it needs (phase 5).
- **Why:** If state changes only by applying events, the event log is complete
  by construction: replay is a fold over the log, needs no seed and no rule
  logic, and keeps working for old logs after rules change. Emitting and
  applying in one call means a plugin writes each state change once and can
  read the updated state right away.
- **Alternatives:** Mutating in `apply_actions` and returning descriptive
  events (the log may then silently miss state); storing only actions and
  re-running the rules for replay (breaks old replays when rules change).
