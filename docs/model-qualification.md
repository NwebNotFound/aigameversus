# Qualifying a model: per route, game and configuration

A proposal, not a spending plan: every live step below costs money and needs
the owner's yes (PROJECT.md). It follows the audit of match `be2f808a`
(research-runs/latest-match-audit) and keeps one rule above all: **a model is
judged only under a configuration that lets it answer.** A rate limit says
something about the provider route at that hour; an answer cut off at the
output limit says something about the limit; neither says the model cannot
use tools.

## What a status is about

A qualification holds for one exact combination, never for a model name
alone:

| Part | Example |
| --- | --- |
| provider model id | `tencent/hy3` (the OpenRouter id, not the display name) |
| route | the provider OpenRouter used, when the answer says it; `:free` is its own route |
| game | `liars_deck`, `werewolf`, `civ` (Werewolf night roles and Civ's `submit_orders` count apart) |
| prompt | `prompt_version`, `thought_headline`, `answer_repair` |
| runtime | `max_output_tokens`, `reasoning_effort`, `tool_choice` (`config/models.yaml` or `limits`) |

Changing any part starts the count again.

## What every move tells (free, from the log)

Since #94 every model move ends in a spectators-only `decision` event. Per
move it gives, apart from each other:

- `answers`, `retries`, `rate_limits` (calls refused as too many requests),
  `cutoffs` (answers that ran into the output limit),
- `fallback` (a random move was played: `rejected`, `timeout`,
  `agent_failed`), and with `answer_repair: "v1"` the `repairs` of a garbled
  but clear call,
- `latency_ms`, tokens in, out and for reasoning.

From these, per combination: **clean** (first answer accepted, no repair),
**repaired**, **retried after refusal**, **cut off**, **rate-limited**,
**replaced by the bot**, p50/p95 latency and cost per decision. The behaviour
report names `cut_off` and `throttled` as reliability reasons of their own,
next to `replaced`; none of them is reported as "no tools".

## Status values

The protocol and its statuses are the Researcher's
([research/QUALIFY.md](../research/QUALIFY.md), #128): **qualified**,
**unqualified** or **unknown**, each with a reason. This page only names the
reasons the arena's own figures give:

| Status | Reason | When | What to do |
| --- | --- | --- | --- |
| unknown | too few moves | fewer than 20 decisions | never rank it |
| unknown | not tested | the catalog lists `tools` and `tool_choice`, nothing played yet | selectable, marked unverified; a declaration certifies nothing |
| unknown | route | the seat failed on rate limits, or more than 20 % of calls were throttled | try again later or another route; no capability judgement |
| unqualified | config | more than 10 % of moves cut off, or refused for the output format | raise `max_output_tokens`, set `reasoning_effort` (or `off`), count again |
| unqualified | unsupported | with enough output room it still answers without a tool call in more than half its moves | not selectable for this game |
| qualified | | ≥ 20 decisions, ≤ 10 % bot moves, ≤ 10 % cut off, every error class shown | ranked |

## Ladder

1. **Free fixtures** (mock LLM, no money): each game's tool schemas, seat
   identity, private-state boundaries, an empty hand, the last legal target,
   a long history, and answers that are cut off, garbled or arrive late. The
   request shape is the real one (`tool_schemas`, `call_options`).
2. **One legal action** per combination: one paid call. Passing it means
   "tool call passed", nothing more.
3. **Short pilot per game**: enough decisions for the status (20+), with the
   figures above. Werewolf night roles and Civ's `submit_orders` are their
   own lines.
4. **Paired comparison** only with frozen runtime settings, seeds and seat
   or role assignments; change one factor at a time (strategy text, then a
   private plan).

## Configuration proposals from the audit (no new calls)

| Model (route) | Seen in `be2f808a` | Proposal |
| --- | --- | --- |
| Tencent Hy3 | 10 of 17 moves had an answer cut off at 1500 tokens; all 17 ended valid | unqualified (config): `max_output_tokens: 4000`; `reasoning_effort: low` if its route takes it, else `off`; re-count |
| MiMo-V2.6-Pro | 1 cutoff in 6 decisions | unknown (too few moves); same output room as Hy3 for its next pilot |
| glm-flash | 1 cutoff, 1 missing `card_ids` in 21 | qualified stays (E1: 80 matches, no agent failure) |
| Gemma 4 26B A4B (`:free`) | first call rate-limited 4 times, seat failed, 10 bot moves | unknown (route): a free route under load; judge it only on a paid route or at another hour |

A higher output limit raises the booking per call (the budget books the
model's own limit), so a pilot with 4000 tokens costs more per call before
the answer settles: estimate it first (`POST /matches/estimate`, `basis`).
