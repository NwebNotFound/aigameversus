# D-099 · Key moments are staged by the watch screen, from the transcript's highlights

- **Date:** 2026-11-11
- **Decision:** The stage reacts to a key moment with a short beat. A call-out
  on its top edge holds the transcript line's own words, and a light effect
  follows the event type: an amber ring for a call or a reveal, a red flash
  and a short jolt for a live chamber, a soft ring for a click, a brass glow
  for an all-in or the end, green for a pot won, and night blue at nightfall
  (`beatOf` in `web/src/lib/viewer.ts`, `Beats.svelte`). A beat plays only for
  what was just watched: live turns, or a replay that plays or moves on by a
  moment. Opening a match, seeking and stepping back stay quiet. The Liar's
  Deck table drops its own banner and its own wording of calls and shots.
  Boards draw the shared avatar, coloured by model. The revolver cylinder turns
  one chamber per pull. Poker seats show their last action of the street, and
  after the last hand there is no pot or odds and a busted seat says "out".
  Werewolf votes draw one after another. With reduced motion, nothing moves:
  there are no flashes, jolts, turns or drawing, and the call-out stays as a
  static label.
- **Why:** One place stages every game's drama in the same rhythm, and its
  words come from the transcript (D-078), not from a second wording in the
  board.
- **Alternatives:** An animation per board component (three ways to time the
  same thing, and a banner text in each); full-screen interstitials (they
  block the board and make fast play tiring).
