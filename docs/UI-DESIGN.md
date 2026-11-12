# Spectator UI design

How AIGameVersus looks and moves. The goal is a match you *watch*, like a card
night on TV: one stage, one commentator, and the secret thoughts of every
player one tap away. Live view and replay are the same screen; a replay just
has a timeline you can scrub.

All art is original, drawn in SVG and CSS in this repository (listed in
`docs/CREDITS.md`). Nothing is taken from other games.

## Look and feel

- **Smoky card room at night.** Deep ink background, one warm key light on the
  table, cool rim light at the edges. The table is the brightest thing on the
  screen; chrome stays dark and quiet.
- **Stage first.** The board takes the most space and sits at the top. Text
  sits beside it (desktop) or under it in a fixed-height drawer (mobile). The
  page never grows without limit.
- **Three voices, three looks.** The *narrator* (headings, results) is set in
  a serif small-caps line. *Speech* is a bubble that comes from the speaker's
  seat. A *thought* is a dashed, tinted cloud with a lock icon, so it can never
  be mistaken for something the other players heard.
- **Motion only for drama.** Calm by default; a short, staged beat for the few
  moments that matter (see Motion).

## Tokens

Defined once in `web/src/app.css`, from the design review (`Shared/AIGameVersus/design/DESIGN-REVIEW.md`,
sections 3.2 to 3.4). Components use tokens, never raw colours. The older names
(`--surface-raised`, `--border`, `--accent`, `--accent-2`) are aliases until every component
uses the new ones.

| Token | Value | Use |
| --- | --- | --- |
| `--bg` | `#0B0D12` | page (no gradient) |
| `--sunken` | `#080A0E` | board well, inputs |
| `--surface` | `#12161F` | cards |
| `--raised` | `#1A202C` | rows inside cards, active tab |
| `--line` / `--line-strong` | `#252C3B` / `#39425A` | hairlines / control borders |
| `--text` | `#E9ECF3` | body |
| `--muted` | `#9AA4B8` | secondary |
| `--faint` | `#626C82` | captions and axis labels only |
| `--brand` | `#F2B84B` | primary button, active tab, "now", warnings about answers |
| `--info` | `#6CB6FF` | links, neutral data bars |
| `--ok` | `#4CD4A0` | pact, honest, correct, clean |
| `--danger` | `#FF6B6B` | war, battle, betrayal, lie, death |
| `--thought` | `#B79CFF` | private thoughts only |
| `--p1` … `--p6`, `--p-neutral` | Okabe-Ito, lightened | player slots (below) |

Players: one identity per player, everywhere (`web/src/lib/players.ts`). The slot is the
seat order (p1 is slot 1) and gives a colour, a shape and a line dash, so colour is never
the only cue: 1 sky circle solid, 2 orange diamond long dash, 3 rose triangle dotted,
4 green square dash-dot, 5 yellow pentagon short dash, 6 vermilion star dash-dot-dot;
barbarians and rebels a slate cross. Tables of more than six (Werewolf) are not coloured by
player. Player colours never carry meaning, and red and green are never an identity.

Shared pieces in `web/src/lib/components/ui/`: `PlayerMark` (emblem), `PlayerName`,
`Chip` (neutral, war, pact, tag, live, warn), `Segmented`, `Tabs`, `Card` (a question
as title, a one-line answer under it), `StatTile` (number with its `/ of`), `DataTable`
(scrolls inside its card).

## Type

Text: `Inter, "Segoe UI", system-ui` (no web font request). Every number that is
compared uses `--font-mono` (`JetBrains Mono`, `Cascadia Mono`, Consolas) with
`tabular-nums` (the `num` class). The serif narrator face is gone: a narrator line is
body text at weight 600.

| Step | Size / line | Weight | Use |
| --- | --- | --- | --- |
| display | 22 / 28 | 650 | the one-sentence answer |
| title | 20 / 26 | 650 | page title |
| question | 15 / 20 | 600 | card question |
| body | 14 / 20 | 400 | feed, paragraphs |
| small | 12.5 / 18 | 400 | tables, meta |
| caption | 11 / 14, +0.06em, upper | 600 | section labels, table heads (`caption` class) |

Spacing on a 4 px grid (4, 8, 12, 16, 24, 40); radius 6 controls, 10 rows, 14 cards; no
shadows; motion 150 ms ease-out, off under reduced motion.

## The watch screen (live and replay)

```
1280                                                        375
┌──────────────────────────────────────────────────┐   ┌───────────────┐
│ Liar's Deck · live ●  match 7 of 112 · €0.43/3.00│   │ title · live ●│
├──────────────────────────────┬───────────────────┤   │ €0.43         │
│                              │ COMMENTARY        │   ├───────────────┤
│          STAGE               │ ── Round 3 ──     │   │    STAGE      │
│   (board, seats, bubbles)    │ Gemini plays 2 …  │   │  (16:10 max)  │
│                              │ ☁ thought (spoil.)│   ├───────────────┤
│                              │ …                 │   │ timeline      │
├──────────────────────────────┴───────────────────┤   ├───────────────┤
│ ◀ ▶ 1×  ▮▮◆▮▮▮◆▮▮▮▮●  R1 R2 R3 …        [mode]   │   │ [Feed|Thoughts│
└──────────────────────────────────────────────────┘   │  |Players]    │
                                                        │ drawer 55vh   │
                                                        └───────────────┘
```

- **Header strip** (one line): game, status (`live` pulses), players as
  avatar chips, cost so far, and for batch runs "match 7 of 112 · €0.43 of
  €3.00". Seed and export live in a "⋯" menu, in Spectator view only.
- **Stage:** about 62% of the width on desktop, full width on mobile. Speech
  bubbles appear at the speaker's seat for a few seconds, then go to the feed.
  The active seat gets the brass rim light; the rest dim a bit.
- **Commentary:** the transcript from `GET /matches/{id}/transcript`
  (`TranscriptLine`, one renderer in `arena/transcript`; the web adds no
  formatter of its own). Rendering by `kind`:
  - `heading`: narrator divider ("── Round 3 · table card: Queen ──");
  - `action`: avatar + sentence;
  - `speech`: bubble with a quote mark, in the seat colour;
  - `whisper`: bubble with an ear icon, visible only in spectator view;
  - `thought`: dashed `--thought` cloud with a lock, only in spectator view;
  - `reveal` and `result`: full-width card, accent or danger edge;
  - `narration`: italic serif small caps;
  - `info`: hidden unless "Show bookkeeping" is on.
  `importance` 3 gets a marker on the timeline and a short glow in the feed.
  The `raw` toggle is kept for developers, off by default.
- **Thoughts tab** (mobile) / filter (desktop): thoughts grouped per player,
  newest first, with a "says vs. thinks" pair when a speech and a thought share
  a turn.
- **Players tab** (mobile) / seat hover card (desktop): name, model, avatar,
  cost so far (ticker, 3 significant digits: "€0.0123"), Elo.

## Viewer modes

Two named modes, a segmented switch in the header, also in the URL
(`?view=spectator|spoiler-free`):

- **Spectator view** (default): thoughts, hands, roles, whispers and chambers
  visible. Marked with the lock-eye icon in `--thought`, so a screenshot always
  shows that it reveals hidden information.
- **Spoiler-free:** hidden information never reaches the browser.
  - The transcript is fetched with `spoilers=false`.
  - The web server, which proxies every arena call (D-030), strips the
    spectator-only events (`visible_to` not null) from the event log and the
    live stream. It also removes the secret board fields (`hand`, `cards`,
    `role`, `win_probability`, the same list the boards already hide) before
    it answers the page.
  - So thoughts, hidden hands, roles, whispers and the revolver chamber are
    neither fetched by the browser nor in the DOM. Face-down cards show their
    backs. Switching back loads the page again in the other mode.
  - The seed and the JSON export are Spectator-view only. The seed gives away
    every hidden draw, and the export holds hands, roles and thoughts.
  - Later, the arena's `GET /matches/{id}/board` could take `spoilers=false`
    and redact in the plugin itself. The web filter then stays as a second
    guard.

## Replay timeline

- A track of segments, one per round, hand, night or day (from `heading`
  lines), labelled "R3", "H12", "N2". Click a label to jump to its start.
- Diamonds for `importance` 3 lines (shot, all-in, death, "Liar!"),
  coloured by kind; hover for the sentence.
- Controls: previous/next *moment* (skips `info`), play/pause, speed 1×, 2×,
  4× and "highlights only". Keyboard: space, ←/→ moment, shift+←/→ chapter.
- The step stays in the address (`?step=`), as now.

## Motion

| Moment | Beat (total) |
| --- | --- |
| Liar's Deck "Liar!" | the caller's seat flashes `--danger`; the cards flip one by one (120 ms apart); hold 600 ms |
| Liar's Deck shot | the screen dims to 40%; the cylinder turns (700 ms); then a flash and a shake for a hit, or a soft "click" ring for a miss |
| Poker all-in | the chips slide to the pot; the pot grows with a brass glow; win % bars appear |
| Poker showdown | the hands flip; the winning five cards lift 6 px; the pot slides to the winner |
| Werewolf night falls | the felt crossfades to night blue (800 ms); the moon rises; the seats dim |
| Werewolf night kill | in the morning the victim's seat fades to grey, a role card flips (spectator view, or when revealed) |
| Werewolf vote | the arrows draw one at a time; the tally bubbles count up |

Rules: transform and opacity only; at most 1.2 s per beat; never block input;
4× speed and "highlights only" shorten beats to 40%.

**Reduced motion** (`prefers-reduced-motion: reduce`): no shake, rotation or
sliding. State changes become 150 ms crossfades, and the highlight is shown as
a static outline. The same holds for the live "pulse".

## Boards

Each board is one Svelte component fed by the plugin's `render_spec`; this
section sets its look.

- **Liar's Deck:** a round burgundy bar top seen from above, with four seats
  on the rim. Each seat shows a card stand (backs, or faces in spectator view),
  a revolver cylinder with six chambers (spent ones marked; the live chamber
  only in spectator view), and the name and model. In the centre: the table
  card large, and the face-down played pile. Nothing is laid over the cards;
  the action line sits under the table card.
- **Poker:** an oval baize table with 2–6 seats on an ellipse (positions
  computed, never overlapping the rail). Each seat shows the hole cards, the
  stack, and an action chip ("raise 120") that fades after the next action.
  The pot is drawn as chips with the amount under it. Win % is a thin bar
  under the cards (spectator view only). Folded seats are greyed and their
  cards tucked.
- **Werewolf:** a village square with seats in a circle and a day/night sky.
  Role cards are readable (≥ 0.75rem) and shown only in spectator view. Dead
  seats become gravestones with their role once it is revealed. Votes are
  drawn as arrows, plus a tally ring per target.
- **Throne of Tokens:** a hex map, to be designed when its `render_spec` lands.

## Other pages

- **Home:** a hero with a looping replay clip of the board, the game cards, and
  "Live now" cards with avatars and a mini board.
- **Replays:** cards rather than a table, with a game colour edge, avatars and
  the winner, length, cost, and the number of highlights; filters for game,
  model and date.
- **Leaderboard:** tabs per game, without internal toy games. Rows show the
  avatar, name and model, Elo with a trend sparkline, and win rate as a bar.
- **Profile:** avatar, model and badge; Elo per game on a common scale; famous
  moments (`importance` 3 lines) linked into replays.

## Checks for every UI PR

- Screenshots at 375 and 1280, before and after, in the PR body.
- Playwright: no horizontal scroll at 375. In spoiler-free mode, no thought,
  hand, role or whisper nodes, no seed text, no export link, and no secret
  field in any response the page fetched. With reduced motion, no running
  animation.
- Contrast ≥ 4.5:1 for text, visible focus, every control reachable by
  keyboard.
