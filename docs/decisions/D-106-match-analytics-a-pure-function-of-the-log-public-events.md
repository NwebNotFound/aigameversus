# D-106 · Match analytics: a pure function of the log, public events only without spoilers

- **Date:** 2026-11-11
- **Decision:**
  - `GET /matches/{id}/analytics?spoilers=` returns per-move rows, per-player
    totals and per-round cells, built on each request from the stored log by
    `arena/analytics/` (one module per game, Liar's Deck first). A running match
    answers with its turns so far; a replay file gives the same numbers.
  - Without spoilers only public events are read. Numbers that need a hidden
    event are `null` (a play's honesty until its cards are turned over, the
    risk at a pull), never estimated. With spoilers everything is read.
  - Every move carries its log position (`seq`), so a chart can jump the
    replay to it.
  - Thinking time and tokens are read from the decision event
    (`action_accepted` / `action_fallback`) once the runner writes them there;
    until then they are `null`.
  - The definitions are in `docs/METRICS.md`; the Liar's Deck totals agree with
    the profile statistics (`arena/stats`), checked by a test.
- **Why:** One rule for hidden information, the same as the transcript's, keeps a
  spoiler-free viewer honest; computing from the log needs no new tables and
  stays correct for imported replays.
- **Alternatives:** stored per-match analytics (stale when a definition
  changes); estimating lies from public data (a guess shown as a number).
