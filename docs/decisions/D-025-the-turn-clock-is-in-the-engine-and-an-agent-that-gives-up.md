# D-025 · The turn clock is in the engine, and an agent that gives up loses its seat

- **Date:** 2026-11-11
- **Decision:** `Match(turn_timeout=60)` limits one turn of one player,
  corrections included. When the time is up, the answer is abandoned and the
  game's `random_action` plays. That costs only this turn; the agent is asked
  again on its next one. An agent that raises `AgentError` is out for the rest
  of the match: the engine logs `agent_failed` once (spectators only) and
  plays random legal actions for the seat without asking again. Every
  `action_fallback` carries a `reason`: `rejected`, `timeout` or
  `agent_failed`.
- **Why:** The engine already owns the fallback and the log, and a clock there
  covers every kind of agent. Per turn rather than per call, because
  spectators wait for turns. Replacing a dead model by random play keeps the
  match and its log complete, which a match with eight players needs more than
  it needs that one seat to play well. Other players are not told: they could
  not tell a human table mate's reason for playing badly either.
- **Alternatives:** A clock per model call inside the runner; skipping the
  turn of a slow player (needs a "do nothing" in every game); ending the match
  when a model fails; counting timeouts towards losing the seat.
