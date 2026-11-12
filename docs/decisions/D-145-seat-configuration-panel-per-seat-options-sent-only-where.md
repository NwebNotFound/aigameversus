# D-145 · Seat configuration panel: per-seat options sent only where the arena lists them

- **Date:** 2026-11-12
- **Decision:** In the new-match form, every model seat gets a "Configure" panel
  (`web/src/lib/components/SeatConfig.svelte`, the model in `web/src/lib/seat-config.ts`).
  - **Options:**
    - answer length (the arena's limit, adaptive, or a number of tokens);
    - thinking (reasoning effort);
    - temperature;
    - a strategy text of the seat's own;
    - memory, answer repair and the thought headline;
    - the private plan (Throne of Tokens only).
  - **Defaults and help:** every option starts as "default", which plays the seat as it would
    be played without the panel. Each option has one line of help.
  - **Presets:**
    - *Careful*: high reasoning, adaptive length, temperature 0.2, headline, a careful strategy.
    - *Fast and cheap*: low reasoning, 400 tokens, no headline.
    - *Aggressive*: temperature 0.9, an aggressive strategy.
    - *Reset* goes back to the defaults.
    - A closed panel says "Default", the preset's name, or the number of changes.
  - **Copy:** "Copy from seat N" and "Apply to all seats" make copies, so the seats do not
    share one configuration.
  - **What is sent:** the form sends a seat's changed options as `seats[i].options` only for
    the keys that `GET /setup` lists in `seat_options` (Builder's per-seat backend).
    An arena without the list gets exactly the request it got before. Options it does not
    take are shown greyed, "Not taken by this arena yet".
  - **Refused values:** an answer length outside 64-8000 tokens, a temperature outside 0-2,
    or a strategy over 600 characters is refused at its seat, before anything is sent.
  - **The live estimate:** `POST /matches/new/estimate`, a proxy for the free
    `POST /matches/estimate` that runs a few hundred milliseconds after a seat changes.
    - It is shown next to the **worst case**: the lower of the match cap and the spend limit
      entered, where the match stops.
    - It warns when the estimate passes the worst case.
    - It says so when models are counted at their output limit, and that the seat options are
      not counted yet.
  - **Read-only:** a read-only request (the LAN page) never reaches the form or the proxy;
    `src/hooks.server.ts` refuses both.
- **Why:** Nils wants more ways to configure the AIs (Lead 8a69b7a2). The backend lands
  separately, from Arena Builder. Sending only listed options lets the form ship first and switch each
  option on when the arena takes it, with no broken request in between.
- **Alternatives:**
  - Waiting for the backend: the form structure and its tests would wait too.
  - Sending every option and letting the arena refuse unknown ones: an older arena would
    refuse every configured match.
  - Hiding unsupported options: viewers would not see what is coming. Showing them greyed
    with a note matches the personality picker.
