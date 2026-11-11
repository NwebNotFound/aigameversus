# D-108 · Every model move says what it took, in a spectators-only event

- **Date:** 2026-11-11
- **Decision:** The engine closes every move of a model, and every move that
  ended in a random one, with a `decision` event visible to spectators only:
  answers, wall time of the move in ms (network and corrections included),
  input, output and reasoning tokens added up over its answers, calls tried
  again, and the fallback reason. The tokens come from the agent's `Reply`
  (`stats`); the time from a `clock` the `Match` gets from the API and the
  command, and is null without one. Bot moves leave no event. The ledger
  keeps latency and reasoning tokens per call (migration 0013); a ledger
  that lacks those columns still gets the cost, without them, so a call
  that was paid never costs its turn over a statistic.
- **Why:** The analytics view (thinking time per move, cost and tokens per
  player, fallback markers) is built from the event log, like everything
  else, so replays show it too. A separate event leaves the events players
  see, and with them every prompt and golden file, unchanged. Timing only
  with a clock keeps test logs deterministic; a bot's time is meaningless.
- **Alternatives:** Fields on `action_accepted` (players see that event in
  their prompt); timing inside the agent (misses the engine's corrections and
  checks); reading the numbers from the ledger only (not in an exported or
  imported log, and not per move).
