# D-129 · A repaired move carries a muted marker per tier; spoiler-free shows the tier and probability only

- **Date:** 2026-11-12
- **Decision:** A move whose answer was repaired (answer_repair, #114 and #141) shows a small muted marker next to it in the commentary, the same in the live view and in replays, never red:
  - **Tier 1** (`decision.repairs`, the call read as meant) shows "repaired". Its tooltip says what was wrong, for example "the call was written inside text".
  - **Tier 2** (`action_accepted.repaired_by: "jev"`) shows "repaired by Jev (p=0.93)". Its tooltip gives the tier, how often the call was refused, the probability and the last refusal.
  - **Red** stays for a random move only (D-113). Tier 2 replaces the retry marker of the same move, because it already tells the refusals.
  - **Spoiler-free:** the web server reads the spectator lines on the server and puts only `{tier, p}` on the public line of the same move (`withRepairMarks`, `transcriptFor`), so the marker shows without a tooltip problem. The refused call, its arguments and the error text never leave the server, as they can name hidden cards.
- **Why:** Lead (2026-11-12): Jev's repairs must be visible, but as answer quality, not as errors. Spoiler-free viewers should see that a move was repaired, without anything a player hid.
- **Alternatives:**
  - An arena field on public lines: the transcript belongs to the arena team, and the web can derive the mark from what it already reads.
  - Showing the problem text in spoiler-free: rejected, since it can name hidden cards.
  - One marker for both tiers: rejected, because tier 2 is a model's guess with a probability and should say so.
