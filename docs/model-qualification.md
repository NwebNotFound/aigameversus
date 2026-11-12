# Model qualification: what the arena's figures give the protocol

The protocol is the Researcher's: [research/QUALIFY.md](../research/QUALIFY.md)
(#128). It decides **qualified**, **unqualified** or **unknown**, with a
reason, for one model, provider route, game and configuration. This note only
says which figures the arena logs for it and how they map onto its reasons.
There is no second protocol here.

## The figures, per model move

Every model move ends in a spectators-only `decision` event (#94, #126):
`answers`, `retries`, `rate_limits` (calls refused as too many requests),
`cutoffs` (answers that ran into the output limit), `fallback` (a random move
was played: `rejected`, `timeout`, `agent_failed`), with `answer_repair: "v1"`
the `repairs` of a garbled but clear call, and `latency_ms` and the tokens.
Per model, `GET /models/catalog` sums them up as `reliability` (#130).

## Mapping onto QUALIFY.md's reasons

| What the figures show | Status : reason |
| --- | --- |
| fewer moves than a verdict needs | unknown : too-few-moves |
| listed with `tools` and `tool_choice`, never played here | unknown : not-empirically-tested |
| the seat failed on rate limits, or many calls were throttled | unknown : route |
| many answers cut off at the output limit, or refused for their format | unqualified : config |
| enough output room, still no tool call in most moves | unqualified : known-unsupported |
| enough moves, few bot moves, few cut-offs | qualified |

A rate limit or a cut-off answer is never read as missing tool support.
