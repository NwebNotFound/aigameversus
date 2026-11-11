# Match metrics

What `GET /matches/{id}/analytics?spoilers=` returns, and what each number means.
The code is `arena/analytics/` (one module per game); it is a pure function of the
stored event log, so a running match, a finished match and a replay file give the
same numbers for the same log.

**Spoilers.** With `spoilers=true` every event is read (the spectator view, also
what players hid). With `spoilers=false` only public events are read
(`visible_to` is null); every number that needs a hidden event is `null`, never
a guess and never 0. The cut is the same as the transcript's.

**Positions.** Every move and pull carries `seq`, its position in the whole log,
so the UI can jump a replay there; `index` is its position among the moves.

## Common fields per move

| Field | Meaning |
|---|---|
| `latency_ms` | Thinking time of the decision: from the request to the model to its answer, network time included (the runner measures the whole call, retries included). `null` for bots and until the runner records it. |
| `tokens_in`, `tokens_out` | Prompt and answer tokens of the decision, as the provider reports them. `null` when unknown. |
| `reasoning_tokens` | Hidden reasoning tokens the provider reports, if any. |
| `retries` | Model calls repeated after an error for this decision. |
| `fallback` | The move was not the model's: the engine played a random legal move (rejected answers, a timeout, or a failed agent). Spectator view only. |

## Liar's Deck

### Moves (`moves`)

- **play** (`kind: "play"`): a `cards_played` event. `cards` is how many cards
  were put face down; `cards_left` the hand size after it.
  - `honest`: true if every card played is the round's table card or a joker,
    false if at least one is not (a **lie**). With spoilers it is known for
    every play (from `cards_hidden`); without, only for plays whose cards were
    turned over (`cards_revealed`), else `null`.
  - `called`: the play was turned over by a call (chosen or automatic).
- **call** (`kind: "call"`): a `liar_called` event. `target` is whose play was
  called; `automatic` is true for the forced call when nobody else holds cards.
  `correct`: the revealed play was a lie (`honest: false`).

A hand-over (`turn_passed`) is not a move: it only says whose turn is next.

### Pulls (`pulls`)

A `trigger_pulled` event: `pull` is the player's pull number, `live` whether it
fired. `risk` is the chance it fires: live chambers / chambers not yet pulled,
at the moment of the pull (0 to 1). It needs the hidden revolver loading, so it
is `null` without spoilers.

### Totals per player (`totals`)

| Field | Definition |
|---|---|
| `plays` | Plays made. |
| `plays_known` | Plays whose honesty is known (all of them with spoilers). |
| `honest`, `lies` | Known plays that were honest / lies. |
| `lie_rate` | `lies / plays_known`; `null` with no known play. Without spoilers it is the rate among **revealed** plays only, which over-weights called plays: compare it only with spoilers. |
| `lies_called` | Lies that were turned over (chosen or automatic call). |
| `calls` | Calls the player chose to make; automatic calls are left out. |
| `calls_correct`, `calls_wrong` | Chosen calls whose revealed play was a lie / was honest. |
| `call_accuracy` | `calls_correct / (calls_correct + calls_wrong)`; `null` without a judged call. |
| `cards_claimed` | Cards put down over all plays (the "bluff size" summed). |
| `pulls`, `pulls_survived` | Trigger pulls, and those that did not fire. |
| `fallbacks` | Moves the engine played instead of the model. |
| `thinking_ms_total`, `thinking_ms_mean` | Sum and mean of `latency_ms` over the player's moves that have it. |
| `tokens_in`, `tokens_out` | Sums over the player's moves that report them. |

These agree with `arena/stats/liars_deck.py` (the profile statistics) for plays,
lies, times caught and calls; a test checks it on bot matches.

### Per round (`by_round`)

For each round and player: `honest`, `lies`, `unknown` (plays with no known
honesty) and `calls`. The cells add up to the totals.

## Poker, Werewolf

Not built yet; they will follow the same layout (moves, totals, per hand or day).
