# D-102 · Any OpenRouter model that can call tools may take a seat

- **Date:** 2026-11-11
- **Decision:** `GET /models/catalog` lists the models of
  `config/models.yaml` (verified, under their own ids) and then every other
  model of OpenRouter's public model list that writes text and supports
  `tools` and `tool_choice`, with vendor, context length, price per million
  tokens and flags for reasoning, moderation, free and high price (output
  above 10 USD per million tokens). `POST /matches` and `arena run --models`
  take any of these ids; an unverified model goes by its OpenRouter id and is
  booked at OpenRouter's listed price times 1.25 (`UNVERIFIED_PRICE_MARGIN`),
  because nobody checked the price and a call may be routed to a dearer
  provider: the caps then stop it early, not late. A model is left out when a
  price is not a finite number from 0 to 10,000 USD per million tokens, and so
  is every id with a `:` variant except `:free` (`:batch` is another API).
  Each entry says its `price_source`. `POST /matches/estimate` takes the
  same ids and prices them as they are booked (x1.25 for unverified ones);
  its answer lists the models above 10 USD per million output tokens in
  `high_price`. The list is cached for an hour, the last copy is used
  when OpenRouter cannot be reached, and without one only the config models
  can play. The cache file (default in the temp folder) is writable by other
  programs of the same user, like the rest of this local stack; the download
  is capped at 20 MB. The caps, `confirm_spend` and the key rules are the same for
  every model. Every model gets the options of `limits` (reasoning effort,
  output limit, a forced tool call); a provider that refuses them gets the
  request once more without them, as before.
- **Why:** The project owner wants to choose any compatible model from the
  launch form, not only the eight that were added by hand. The price is what
  the caps count with, so it has to come from the same place the bill comes
  from; OpenRouter publishes it with the list. `tool_choice` is required
  because the runner forces a tool call: a model without it answers in prose.
- **Alternatives:** Adding models to `config/models.yaml` by hand (slow, and
  the owner cannot do it from the UI); allowing models without
  `tool_choice` (they could not be forced to move); options per model from
  OpenRouter's metadata (a second source of behaviour to keep right; the
  retry without options already covers a refusal).
