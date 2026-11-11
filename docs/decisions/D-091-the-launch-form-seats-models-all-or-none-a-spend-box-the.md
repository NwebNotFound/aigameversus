# D-091 · The launch form seats models: all or none, a spend box, the month in view

- **Date:** 2026-11-11
- **Decision:**
  - `GET /setup` says `model_seats: true` only when the server allows model
    seats (`ARENA_ALLOW_MODEL_SEATS=1`) and has the providers' keys, and lists
    each model with its display name and its prices per million tokens.
    `GET /ledger/month` returns what this calendar month (UTC) has cost, the
    month cap and what is left.
  - In `/matches/new` every seat is a random bot or a model from that list. A
    match is all bots or all models, because `POST /matches` takes one model
    per seat. With models the form shows that the match spends real money, its
    cap (the per-match cap, 0.50 EUR), the month's spend and what is left, and
    it needs a ticked box before it starts (`confirm_spend`). With nothing left
    this month it cannot start; with less left than one match may cost it warns.
  - Personalities, thinking effort and a per-run budget stay disabled: the API
    does not take them per seat yet. The cost estimate comes with the arena's
    estimate endpoint.
- **Why:** Starting a paid match must be a deliberate act with the price in
  view; the server stays the only place that refuses a spend.
- **Alternatives:** mixed tables of bots and models (not in the API yet); an
  estimate computed in the browser from token guesses (the arena's endpoint
  will know the prompt sizes).
