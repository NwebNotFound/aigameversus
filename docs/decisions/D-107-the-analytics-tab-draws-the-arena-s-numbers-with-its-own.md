# D-107 · The Analytics tab draws the arena's numbers with its own small SVG charts

- **Date:** 2026-11-11
- **Decision:** Live matches and replays get an Analytics tab next to Watch
  (and Chronicle). It shows the arena's `GET /matches/{id}/analytics`
  (D-106, `docs/METRICS.md`) as charts drawn in plain SVG and CSS, with no
  chart library. Liar's Deck comes first; the other games say "coming".
  - **Key numbers:** moves, lie share, lies caught, pulls fired, and mean
    thinking time.
  - **Charts:**
    - a strip of every move per player (honest, lie, not shown, right or
      wrong call; ring = called, dot = slow, "r" = random fallback);
    - honesty and calls per player as stacked bars, with lie rate and call
      accuracy;
    - a player × round heatmap of the lie share;
    - trigger pulls with their risk;
    - cards left over the match;
    - thinking time per move, with slow outliers (above the median plus 2.5
      median absolute deviations).
  - **Replay:** the numbers stop at the step on screen. The web cuts the
    moves at that event and sums them again (`upTo`). On the full log that
    gives exactly the arena's totals; a test checks it on a real
    four-model match, in both views. Clicking a move, a round or a pull
    jumps the replay there.
  - **Live:** the tab fetches again as turns arrive.
  - **Spoiler-free:** the web server asks the arena with `spoilers=false`,
    so no hidden truth reaches the browser.
- **Why:** Nils wants to see thinking time, lies, honest plays and caught lies
  "in multiple ways like graphs". The charts are few and simple, so a library
  (tens of kB, its own look, its own colours) would cost more than it saves.
  Every number stays the arena's; the web never defines a metric of its own.
- **Alternatives:** A chart library (bigger bundle, harder to match the
  palette and display names); the arena computing analytics per replay step
  (a request per step while scrubbing).
