# What data each game offers

An audit of 2026-11-12, re-checked against main at `5cb1258`, by running a bot match of every
game against each entry point (Liar's Deck 3 players, Poker 3, Werewolf 8, Throne of Tokens 4
for 6 rounds). **Gaps are marked ✗**; an open pull request that closes one is named. Update
this table in the pull request that closes a gap.

## Per match

| Entry point | Liar's Deck | Poker | Werewolf | Throne of Tokens |
| --- | --- | --- | --- | --- |
| Transcript, en and de (`GET /matches/{id}/transcript`) | ✓ | ✓ | ✓ | ✓ public lines, city counts per round |
| Situation: how it is going, in words and facts (`analytics.situation`) | ✓ | ✓ | ✓ | ✗ `null` |
| Per-move and per-player numbers (`GET /matches/{id}/analytics`) | ✓ plays, calls, lies, shots, per round | ✓ hands, chips series, moves, rates, showdown bluffs (#169) | ✓ votes, claims, accusations, stance, recaps | ✓ `civ/1`: series per nation, battles, conquests, diplomacy, orders, decisions |
| Report: at a glance, ranking, key moments (`analytics.report`) | ✓ | ✓ few columns (chips, pots won, biggest pot) | ✓ with awards | ✗ none (`civ/2` adds it: #190 open) |
| Behaviour tags (`analytics.behaviour`) | ✓ bluffer, caller, risk-taker | ✗ | ✗ | ✓ counts and tags (wars, attacks, broken treaties, trades) |
| Table-talk checks against the engine's truth (`GET /matches/{id}/talk-checks`, D-122) | ✓ hand and play statements | ✓ hand statements | ✓ role claims | n/a (no talk checks yet) |
| Chronicle, four styles (`GET /matches/{id}/chronicle`) | ✓ from facts | ✓ old template text (#184 open: chapter per blind level) | ✓ from facts | ✗ none (#183 open) |
| AI-written chronicle (`POST /matches/{id}/chronicle/ai`, D-140) | ✓ | ✓ | ✓ | ✗ (follows the chronicle) |
| Post-match referee (Jev, gated, `POST /matches/{id}/referee`; picks moments by rule, whatever the game) | ✓ | ✓ | ✓ | not tried |
| Decision telemetry per move (latency, tokens, retries, cut-offs, repairs; `decision` events) | ✓ | ✓ | ✓ | ✓ |
| Board for the web (`render_spec`) | ✓ | ✓ | ✓ | ✓ hex map |

## Lists and per player or model, across matches

| Entry point | Liar's Deck | Poker | Werewolf | Throne of Tokens |
| --- | --- | --- | --- | --- |
| Match list (`GET /matches`) | ✓ `game` filter, `limit`/`offset`, `X-Total-Count`, one-line `outcome` per row (#186) | ✓ | ✓ | ✓ |
| Rating per game and overall (leaderboard, model page) | ✓ | ✓ | ✓ | ✓ |
| Played but not rated, with the reason (`unrated` on the leaderboard and the model page, #181) | ✓ API; the page does not show it yet (Designer) | ✓ | ✓ | ✓ |
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

1. **Poker per-match analytics** is on main (#169): chips over the hands, hands won, showdown
   results, fold/call/raise/all-in rates, bluff and value-bet rate from showdown truth,
   aggression and the decision telemetry. The Poker tab in the web does not draw it yet.
2. **Exports** for every game: a match file with analytics, a model CSV.
3. **Throne of Tokens** has analytics (`civ/1`) and behaviour tags, but no situation, no
   report (`civ/2` adds per-round decisions and orders, treaty end rounds, `key_moments` and a
   `turning_point`: #190 open), no per-profile statistics and no chronicle (#183 open).
4. **The match list** can be filtered by game and paged (#186); the web page still lists a fixed
   page.
5. **Behaviour tags** exist for Liar's Deck and Throne of Tokens only; Poker (tight/loose,
   passive/aggressive from the statistics) and Werewolf (liar, accuser, follower) can follow
   from the numbers once they exist.
6. **The Designer's pages** do not show the played-but-not-rated list yet (the API is on main).

## Spoilers

Numbers that need hidden cards or roles (real hands, who lied, which role) are in the analytics
and export only with `spoilers=true`; without it they are `null`, as in the analytics today. A
number that only the engine's spectator-only events carry (refused answers, bot moves) is also
`null` without spoilers: unknown, not zero.
