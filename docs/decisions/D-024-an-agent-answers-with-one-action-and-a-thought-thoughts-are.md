# D-024 · An agent answers with one action and a thought; thoughts are an engine channel

- **Date:** 2026-11-11
- **Decision:** `Agent.act` returns a `Reply`: exactly one `Action`, or a
  `problem` when there is no usable action (a model that only talked, or sent
  arguments that are not JSON), plus an optional `thought`. The engine records
  a thought as the engine event `thought` with `visible_to=()`: spectators
  only, not even its author gets it back. A `problem` is treated like any
  rejected action: logged, returned as the error, counted as a correction.
  Still one action per request (D-012); of several tool calls in one answer
  the first counts. Messages to other players are game tools, not a third
  field of the reply.
- **Why:** Thoughts exist in every game and must never leak, so one place in
  the engine handles them instead of one tool per plugin, and a plugin cannot
  get their visibility wrong. A model does not need its old thoughts back to
  play, and never feeding them into a prompt removes the path by which they
  could reach another player. Keeping "no action" inside the reply keeps the
  correction loop in the engine, the only place that validates.
- **Alternatives:** A `think` tool per plugin; thoughts visible to their
  author; an exception for unusable answers (the thought of that answer would
  be lost); a batch of actions per reply.
