# What data each game offers

An audit of 2026-11-12 (main at the time of writing), checked by running a bot match of every
game against each entry point. **Gaps are marked ✗**; a number in brackets is the PR or
decision that closes it. Update this table in the pull request that closes a gap.

## Per match

| Entry point | Liar's Deck | Poker | Werewolf | Throne of Tokens |
| --- | --- | --- | --- | --- |
| Transcript, en and de (`GET /matches/{id}/transcript`) | ✓ | ✓ | ✓ | ✓ (public lines, city counts per round) |
| Situation: how it is going, in words and facts (`analytics.situation`) | ✓ | ✓ | ✓ | ✗ |
| Per-move and per-player numbers (`GET /matches/{id}/analytics`, `numbers`) | ✓ plays, calls, lies, shots, per round | ✗ only the report below | ✓ votes, claims, accusations, stance, recaps | ✗ 404 "No analytics for civ yet" |
| Report: at a glance, ranking, key moments (`analytics.report`) | ✓ | ✓ chips, pots won, biggest pot (few columns) | ✓ with awards | ✗ |
| Behaviour tags (`analytics.behaviour`) | ✓ bluffer, caller, risk-taker | ✗ | ✗ | ✗ |
| Table-talk checks against the engine's truth (`GET /matches/{id}/talk-checks`, D-122) | ✓ hand and play statements | ✓ hand statements | ✓ role claims | n/a (no talk checks yet) |
| Chronicle, four styles (`GET /matches/{id}/chronicle`) | ✓ from facts | ✓ old template text | ✓ from facts | ✗ |
| Post-match referee (Jev, gated, `POST /matches/{id}/referee`; it picks moments by rule, whatever the game) | ✓ | ✓ | ✓ | not tried |
| Decision telemetry per move (latency, tokens, retries, cut-offs, repairs; `decision` events) | ✓ | ✓ | ✓ | ✓ |
| Board for the web (`render_spec`) | ✓ | ✓ | ✓ | ✓ hex map |

## Per player or model, across matches

| Entry point | Liar's Deck | Poker | Werewolf | Throne of Tokens |
| --- | --- | --- | --- | --- |
| Rating per game and overall (leaderboard, model page) | ✓ | ✓ | ✓ | ✓ |
| Game statistics (`GET /profiles/{id}/stats`, `arena/stats`) | ✓ | ✓ VPIP, aggression factor, bluff rate, net chips | ✓ | ✗ |
| Cost, tool errors, repaired and clean share, reliability (model page) | ✓ | ✓ | ✓ | ✓ |

## Exports

| What | Today | Gap |
| --- | --- | --- |
| One match, replayable | ✓ web `/replays/{id}/export.json` (`aigameversus-replay/1`: record, cost, the whole log as a spectator sees it); `arena run --save` | ✗ no analytics inside, no server endpoint (the web builds it) |
| One match, readable | ✓ transcript text and Markdown, chronicle `.md` | |
| One match, numbers | ✗ | `GET /matches/{id}/export`: log plus analytics |
| One model, many matches | ✗ | `GET /models/{id}/export`: CSV, one row per match and seat |

## Gaps in order of what Nils asked for

1. **Poker per-match analytics** has no numbers behind it: only the situation and a five-column
   report. Needs chips over the hands, hands won, showdown results, fold/call/raise/all-in
   rates, bluff and value-bet rate from showdown truth, aggression, and the decision
   telemetry per player. (Next PR: `numbers` for poker in the analytics route.)
2. **Exports** for every game: a match file with analytics, a model CSV.
3. **Throne of Tokens** analytics, report, statistics and chronicle are Builder's and Heavy's
   (Civ analytics waits for real logs; bot logs are enough to start).
4. **Behaviour tags** exist for Liar's Deck only; Poker (tight/loose, passive/aggressive from
   the statistics above) and Werewolf (liar, accuser, follower) can follow from the numbers
   once they exist.
5. The Poker chronicle is still the old template text; the rewrite from facts is queued.

## Spoilers

Numbers that need hidden cards or roles (real hands, who lied, which role) are in the analytics
and export only with `spoilers=true`; without it they are `null`, as in the analytics today.
