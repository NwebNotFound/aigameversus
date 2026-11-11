# D-110 · Matches play out at reading pace, live and in replays, whatever the models' speed

- **Date:** 2026-11-11
- **Decision:** A playout director (`web/src/lib/pacing.ts`) decides how long
  each moment stays on screen at 1×:
  - speech and thoughts: 0.3 s plus 60 ms per word, between 0.9 and 6 s;
  - highlights (a call, a shot, a death, a vote result): 2.2 s;
  - a new round, hand, night or day: 1.4 s;
  - a play, a bet or a vote: 1 s;
  - bookkeeping: 0.25 s;
  - a moment with several lines adds 0.2 s per extra line.

  Speeds of 0.5× to 4× divide these times, with a floor of 120 ms. Replays
  play moment by moment with these times, in normalised time: how long a
  model really took is never replayed.

  The live view keeps a playout buffer behind the stream:
  - events arrive as fast as the models answer, and the screen follows moment
    by moment at the chosen playback speed;
  - joining a running match starts at its newest moment;
  - "N moments behind · Jump to live" appears when the screen trails by more
    than two moments;
  - the board shows the position on screen.

  At live, the seat being asked shows "thinking… 12 s" with a gentle pulse
  (none with reduced motion). The time runs from the arena's `asking` start
  when it sends one, else from the last event. After an answer, the chip
  shows the last response time from the decision event.
- **Why:** Nils: "some models take reasonably long, others just do the tool
  call and the whole round blasts through". A burst of instant moves was
  drawn in one frame, and a slow model left a frozen screen. Reading time
  depends on what is shown, not on how fast the model was.
- **Alternatives:** Replaying the real latencies (one slow model makes a replay
  unwatchable, and fast ones still blast through); a fixed time per event
  (bookkeeping gets as long as a shot, and speech too little to read); asking
  the arena to slow down (its `turn_delay` also slows the models' match and
  the research runs).
