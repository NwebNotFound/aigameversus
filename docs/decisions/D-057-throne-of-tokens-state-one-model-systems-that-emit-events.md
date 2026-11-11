# D-057 · Throne of Tokens state: one model, systems that emit, events that carry outcomes

- **Date:** 2026-11-11
- **Decision:** The game has one state model, `CivState` in
  `games/civ/state.py`, and each system is a module of functions over it
  (`games/civ/economy.py` is the first). A function that changes something
  takes the engine's `TurnContext` and emits events; the module's
  `apply_event` is the only code that writes to the state. An event carries
  what happened in numbers (the cost paid, the refund, the nation's new
  stock), never a reference to a rule, so applying it reads no game data.
  The production of a nation in a round is one event. Every economy event
  is private to its nation. Each order has a `*_problem` function that
  returns a message for the player or `None`.
- **Why:** This is D-009 one level down: the plugin of step 7.6 passes its
  context through and routes events back, and the log rebuilds the state
  with no rules and no data files. Private events keep the fog honest: a
  public "city founded" would give its tile away. One event per nation and
  round keeps a player's recent events, which the prompt shows 40 of, from
  being pushed out by bookkeeping. The check is separate from the order
  because the plugin needs it twice: when a model submits its orders, to
  ask for a correction, and when the round is resolved.
- **Alternatives:** Pure functions that return events for the plugin to
  emit (every step would have to be re-applied by hand before the next one
  can read its result); a state per system (cities are read by fog, combat
  and victory alike); events that name the rule and let `apply_event` look
  the numbers up (an old log would change its meaning when a number is
  tuned); one event per city and round.
