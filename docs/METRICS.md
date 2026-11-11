# Match metrics

What `GET /matches/{id}/analytics?spoilers=` returns, and what each number means.
The code is `arena/analytics/` (one module per game); it is a pure function of the
stored event log, so a running match, a finished match and a replay file give the
same numbers for the same log. The definitions follow the Researcher's review
(validity for papers).

## Rules for every game

- **Spoilers.** With `spoilers=true` every event is read (the spectator view,
  also what players hid). With `spoilers=false` only public events are read
  (`visible_to` is null), plus the match start without its seed and with only
  the settings anyone may read; every number that needs a hidden event is
  `null`, never a guess and never 0. The cut is the same as the transcript's.
  Selection-biased numbers (a lie rate over revealed plays only) are not shown
  without spoilers at all: a spoiler-free view gets public counts.
- **Rates carry their n.** A rate is `{"value", "n", "of"}`: `n / of`, with
  `value: null` when `of` is 0. "No data" is `null`, never 0.
- **Fallbacks are not the model's.** A move the engine played for a model
  (`action_fallback`: rejected answers, a timeout, a failed agent) is flagged
  `fallback: true` on every move and left out of every skill number (lie rate,
  call accuracy, ...). It counts only in the reliability numbers
  (`fallback_share`, `rejected_per_move`).
- **Across matches** (batch analytics, not built yet): intervals come from
  resampling whole matches, not single moves, because the moves of one match
  are not independent.
- **Positions.** Every move and pull carries `seq`, its position in the whole
  log, so the UI can jump a replay there; `index` is its position among moves.
- **What the match was.** `meta` holds the game `version`, `prompt_version`,
  `settings` and `seed` (spoilers only) from `match_started`, and `seats` (seat
  to model id; `null` for a bot) from the match record, so comparisons group
  like with like. The arena's code version is not in the log yet.

### Per move: cost of the decision

| Field | Meaning |
|---|---|
| `latency_ms` | **Response time**, not thinking time (thinking is not measurable from outside): wall clock per model call, measured in the arena from sending the request to the full answer, network and provider queue included, `turn_delay` excluded. Per move it is the sum over all calls of the move, corrections included. `null` for bots and until the runner records it. |
| `tokens_in`, `tokens_out` | Prompt and answer tokens of the move's calls, as the provider reports them. |
| `reasoning_tokens` | Hidden reasoning tokens the provider reports: the proxy for thinking. |
| `retries` | Model calls repeated after an error for this move. |
| `rejected` | Answers of this move the engine rejected (each one led to a correction). |
| `fallback` | The engine played this move (see above). |

## Sections (`sections`, `numbers`)

Every answer lists the parts it has besides `game`, `spoilers`, `events` and
`meta`, in order: `["situation"]` for a game with a situation only (Poker
today), `["situation", "players", "moves", ...]` for Liar's Deck. A client
checks this list instead of probing for keys. `numbers` is `false` when the
answer has the situation only, `true` otherwise.

## Situation (`situation`), every game with one

"How is the game going?" at the end of the log read: `situation.facts` (numbers)
and `situation.lines.en` / `.de` (a few short sentences, the same number in both
languages, display names, never a seat id). Liar's Deck, Poker and Werewolf have
one; a game with a situation but no other analytics yet answers with the
situation only. Built from the same events as the rest, so without spoilers it
reads public events only (`arena/analytics/situation.py`).

- **Liar's Deck:** round, table card, whose turn, cards left per player (the
  public count of cards played), pulls survived, the risk of each player's next
  pull (public, as for `pulls`), the player closest to elimination (highest risk
  of those who have pulled), the last call (who called whom, whether the cards
  were honest once revealed, who pulled and whether they survived), the winner.
- **Poker:** hand, street, pot, every stack (starting stack, minus blinds and
  bets, plus pots won; chips always add up), chip leader, all-in players (stack
  0, still in the hand, chips in the pot), short stacks (under 10 big blinds),
  the biggest pot so far, the winner or the hand limit.
- **Werewolf:** night or day and its number, alive of all, votes cast today per
  target, the last death with its public role and cause, the winner. **Teams
  alive** (village, wolves, on their own) only with spoilers: roles are private
  until a player dies.

## Behaviour (`behaviour`), Liar's Deck so far

Per player: `tags` (descriptive style tags with their evidence), `too_early`,
`compare` and, with spoilers only, `last_thought` (the player's latest thought,
cut to 200 characters). The thresholds are constants in
`arena/analytics/behaviour.py`; they are a first proposal, reviewed by the
Researcher.

Rules for every tag:

- **Minimum sample:** no tag below 10 own decisions of the kind it describes
  (plays, call opportunities, moves). Fallback moves never count. A player with
  fewer than 10 own moves gets `too_early: {n, need: 10}` ("too early to tell").
- **Clear of the threshold:** a rate tag appears only when its whole Wilson 95 %
  interval lies on the right side: the lower end above the threshold for a
  "often" tag, the upper end below it for a "rarely" tag. 7 lies in 10 plays is
  not a Bluffer yet (interval 40-89 %); 25 in 35 is (55-84 %). The tag's `text`
  states the rate, the interval and n.
- **Views:** tags from hidden cards (Bluffer, Honest, Sharp eye, Risk-taker) or
  from private events (Rule-breaker, Often replaced by the bot) appear only with
  spoilers (`spoilers: true` on the tag).

| Tag | Rule | n |
| --- | --- | --- |
| Bluffer | chosen-lie rate (lies when an honest card was in hand) above 0.5 | ≥ 10 such plays |
| Honest | chosen-lie rate below 0.15 | ≥ 10 such plays |
| Cautious | call rate below 0.15 of call opportunities | ≥ 10 opportunities |
| Trigger-happy | call rate above 0.5 | ≥ 10 opportunities |
| Sharp eye | hit rate at least 0.2 above the false-alarm rate, and their intervals do not overlap | ≥ 10 on each side |
| Risk-taker | at least 3 lies at a revolver risk of 0.33 or more, and at least half of the plays at that risk were lies; the text names both counts | ≥ 10 plays |
| Rule-breaker | refused answers per own move above 0.25 | ≥ 10 moves |
| Often replaced by the bot (`kind: reliability`) | fallback share above 10 % | ≥ 10 moves |
| Slow / Quick to answer | median response time above 2× / below 0.5× the other seats' median; includes network and provider queue | ≥ 10 moves on both sides |

`compare` puts each rate (`call_rate`, `call_accuracy`, and with spoilers
`chosen_lie_rate`) against the other seats of the match pooled: `above` when the
player's interval lies wholly above theirs, `below` wholly below, `about` when
they overlap, `too few` under 10 on either side. The UI says "clearly above/below" and "about the same",
never "average". `call_accuracy` depends on how often the others lie, which is
fine within one match; a cross-match view compares hit and false-alarm rates
instead.

Speed tags need response times, which come with the per-move `decision` events
(#94); until then no player gets one.

## Liar's Deck

### Moves (`moves`)

- **play** (`kind: "play"`, a `cards_played` event):
  - `cards`: cards put face down; `hand_before`, `cards_left`: hand size before
    and after.
  - `table_cards_held`: table cards plus jokers in the hand at that moment
    (spoilers).
  - `honest`: every card played is the table card or a joker. A **lie** is a
    play with at least one card that is neither. Known for every play with
    spoilers (from `cards_hidden`); without them only for plays whose cards
    were turned over (`cards_revealed`), else `null`.
  - `false_cards`, `lie_size`: cards that were not the table card or a joker,
    and their share of the cards played (spoilers).
  - `forced`: a lie the hand left no choice about (it held no table card and no
    joker); `false` for a **chosen** lie; `null` for honest or unknown plays.
  - `called`: the play was turned over by the next call (chosen or automatic).
  - `could_call`, `facing_lie`: a play was on the table that this player could
    have called instead, and whether it was a lie (see call opportunities).
  - `risk`: the player's own revolver risk at that moment (see pulls).
- **call** (`kind: "call"`, a `liar_called` event): `target` is whose play was
  called; `automatic` marks the forced call when nobody else holds cards.
  `correct`: the revealed play was a lie. `facing_lie` as above.

A hand-over (`turn_passed`) is not a move: it only names whose turn is next.

### Call opportunities

A **call opportunity** is a turn on which `call_liar` was offered: the player's
own move came with a play by someone else on the table. The player either called
(a call) or played on (a play with `could_call: true`). Automatic calls are not
choices and are left out everywhere.

### Pulls (`pulls`)

A `trigger_pulled` event: `pull` is the player's pull number, `live` whether it
fired. `risk` (also on each play and call) is live chambers / chambers not yet
pulled of that player's own revolver at that moment, so later pulls are riskier.
It needs no spoilers: the variant says how many chambers are live
(`revolver.live`), the pulls are public, and a live pull ends the player; only
where the bullets sit is hidden.

### Totals per player (`totals`)

Skill numbers use the model's own moves only (fallbacks left out).

| Field | Definition |
|---|---|
| `plays`, `plays_known` | Plays made; those whose truth is known. |
| `honest`, `lies` | Known plays that were honest / lies. |
| `lie_rate` | lies / plays_known (spoilers only: over revealed plays it would be biased towards called plays). It mostly measures the cards dealt; see `chosen_lie_rate`. |
| `chosen_lie_rate` | chosen lies / plays where an honest play was possible (the hand held a table card or joker) (spoilers). |
| `forced_lies` | Lies with no honest play possible (spoilers). |
| `mean_lie_size` | Mean `lie_size` over lies (spoilers). |
| `lies_called` | Lies that were turned over, by a chosen or an automatic call (apart from the chosen-call figures below). |
| `calls`, `calls_correct`, `calls_wrong` | Chosen calls, and those whose revealed play was a lie / was honest. |
| `call_accuracy` | correct calls / judged calls. It depends on how often the others lie: read it with the next two. |
| `call_rate` | calls / call opportunities. |
| `hit_rate` | calls on lies / opportunities facing a lie (spoilers). |
| `false_alarm_rate` | calls on honest plays / opportunities facing an honest play (spoilers). |
| `cards_claimed` | Cards put down over all plays. |
| `pulls`, `pulls_survived` | Trigger pulls, and those that did not fire. |
| `fallbacks`, `fallback_share` | Moves the engine played, and their share of all the player's moves. |
| `rejected_per_move` | Rejected answers per move. |
| `response_ms_total`, `response_ms_mean` | Sum and mean of `latency_ms` over moves that have it. |
| `tokens_in`, `tokens_out`, `reasoning_tokens` | Sums over moves that report them. |

With spoilers, plays, lies, times caught and calls agree with
`arena/stats/liars_deck.py` (the profile statistics); a test checks it.

### Per round (`by_round`)

For each round and player: `honest`, `lies`, `unknown` (plays with no known
truth), `calls` and `fallbacks`.

### One row per move

`moves` is the per-move table a paper needs: round, cards in hand, table cards
plus jokers held, cards played, truth, called or not, risk, response time and
tokens. The research export will write it as one row per move.

## Poker (planned)

- VPIP and PFR the standard way (blinds and a free check excluded). Aggression
  factor = (bets + raises) / calls, `null` with no call.
- A **bluff** is a bet or raise when the hand's equity against random hands at
  that street is below 0.33; a **value bet** above 0.6. Equity from a seeded
  Monte Carlo with a fixed, documented number of samples, stored per decision;
  the win-probability curve uses the same function. Showdowns alone do not
  define bluffs: most bluffs never reach one.

## Werewolf

`arena/analytics/werewolf.py`. Facts from the game's events, and readings of
speech by simple rules, each marked `heuristic: true`.

- **`votes.days`** (facts): per day `votes` (voter to target; `null` for an
  abstention), `abstained`, `tally` (the game's own count, in which a captain's
  vote may weigh double; abstentions are not in it) and `executed`.
- **`votes.accuracy`** (spoilers only): per village-side voter, votes for a wolf
  / votes cast, as `{value, n, of}`; abstentions are not votes. Planned: for
  wolves, the share of votes on fellow wolves (bussing).
- **`claims`** (heuristic): a sentence in the first person that names a role
  ("I'm p3, a villager", "I am the seer", "Ich bin die Seherin"), not negated.
  Each claim once per player and role, with `changed_from` (the same player
  claimed another role before), `counterclaimed_by` (others who claimed the
  same unique role), and `disproved` / `true_role` when the player's death
  revealed another role.
- **`accusations`**: a vote is an accusation of its target (`source: vote`,
  a fact). A sentence that names a seat (its id or display name, as a whole
  word) next to accusing words (suspect, wolf, lying, …; verdächtig, lügt, …)
  accuses it (`source: speech`, heuristic). A negation in the sentence
  ("not", "nicht") makes it neither; the speaker never accuses themselves.
- **`stance`**, per event seq: `{player, votes_for, suspects, defends, claims,
  heuristic}`; a vote's stance gets the `reason_seq` of the reason that follows
  it, and that reason is not counted again as speech.
- **`phases`** and **`recap`**: each night and day, with its deaths (the
  morning's deaths belong to the night), the most accused player of the phase
  (speech), the tally and the execution; `recap[].text.en/de` is one sentence
  per phase from a template (`TemplateNarrator`). A `Narrator` with the same
  method can replace it, such as a cheap model later; none is called by default.
- Without spoilers only public events are read: no wolf chat, no lover chat,
  no roles but those revealed at death (`meta.revealed`); `meta.roles` is
  null.
