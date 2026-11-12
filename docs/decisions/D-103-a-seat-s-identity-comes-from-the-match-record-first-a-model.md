# D-103 · A seat's identity comes from the match record first; a model seat never reads as a bot

- **Date:** 2026-11-11
- **Decision:** The web builds each seat from all the sources it has
  (`mergeSeats` in `web/src/lib/viewer.ts`):
  - the match record's `seats` (name, model id, kind), which exists for
    running and finished matches;
  - then the transcript's `players`, whose name wins when it gives a profile
    name;
  - then the model roster of `GET /setup`, for the vendor (the provider path
    before "/") and the price per million tokens.
  Every chip, avatar, commentary line, board seat and result card reads this
  one map. A chip shows:
  - the name and a kind badge (model or bot);
  - the model id when the name does not already say it, and the vendor;
  - a personality when the record has one, and the cost so far.
  The tooltip adds the price per million tokens. Avatar colours follow the
  vendor.
- **Why:** On the first real-model match, the chips read "random bot" for
  every seat. The transcript's `players` was empty for a running match while
  the record already knew each seat. A seat's identity must not depend on one
  endpoint being complete.
- **Display names:** every visible name is a display name, computed once per
  match (`withDisplayNames`) unless the API sends `display`:
  - a model is its short name (the profile name, else the model id), with
    "#2" for its second seat;
  - bots are "Bot 1", "Bot 2", in seat order, with "Random Bot" as the small
    line under the name;
  - the seat id appears only as a small number badge on the board
    (`SeatTag`).
  Until the transcript names players itself, the web swaps seat ids in its
  sentences for display names (`namedText`, `namedLines`, applied once where
  the page reads the transcript). This changes names only, never wording.
  Player-written words (speech, thoughts) are shown as written.
- **Alternatives:** Waiting for the transcript to fill `players` for every
  match (the fix belongs there too, and Arena Coder has it); a colour per
  model (the same company's models then look unrelated).
