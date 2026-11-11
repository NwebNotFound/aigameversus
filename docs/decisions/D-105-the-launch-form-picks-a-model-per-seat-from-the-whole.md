# D-105 · The launch form picks a model per seat from the whole catalog

- **Date:** 2026-11-11
- **Decision:**
  - Each seat of `/matches/new` has a picker over `GET /models/catalog`
    (D-102): random bot, or any model in it, verified ones first. It searches
    name, id and vendor (every word must match) and filters by output price
    (up to $1, $3, $10 per million tokens), reasoning, verified and
    favourites; it lists at most 60 at a time, and the search narrows it.
    Each model shows its OpenRouter id, price in and out per million tokens,
    context and tags (verified or unverified, reasoning, free, high price).
  - Shortcuts: "same as p1 in every seat", "fill with cheap models" (the
    cheapest verified paid models, different ones first; free models left out
    because their providers throttle them) and "all random bots".
  - Favourites are kept in the browser (`localStorage`), not on the server.
  - A seat with a high-price model (output above $10 per million) gets a
    warning; unverified models are named under the seats. The caps and the
    spend box hold for every model.
  - The form sends any catalog id; without the catalog it falls back to the
    verified models of `GET /setup`. The arena checks the id again.
- **Why:** Nils wants every compatible OpenRouter model selectable; 389
  models need search and filters, and the price must be visible before a seat
  is filled.
- **Alternatives:** a plain select (unusable at this length); favourites per
  server user (there is no login); free models in "fill with cheap" (they
  stall on their rate limits).
