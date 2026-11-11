# D-036 · `config/models.yaml`: limits and prices next to the roster

- **Date:** 2026-11-11
- **Decision:** `config/models.yaml` has two parts. `limits`: the caps in
  euros (0.50 per match, 5.00 per month, D-001), the dollar-to-euro rate, and
  the token limits of one call (50 000 in, 1 500 out). `models`: id,
  `provider`, the provider's model name and the two prices in US dollars per
  million tokens. The default roster is eight cheap OpenRouter models from
  eight vendors that support tool calls, with the prices openrouter.ai listed
  on 2026-11-11. The rate is 1.0: a dollar counts as a full euro. `provider`
  accepts only `openrouter` for now. `arena/config.py` validates the file;
  unknown fields are errors. `tier` and `base_url` from the spec are left out
  until something reads them (tool sets per model size, local models).
- **Why:** The caps are only as good as the prices, so prices sit in a file
  that people review, next to the model they belong to, in the unit the
  provider publishes. A rate of 1.0 errs on the safe side while a dollar is
  worth less than a euro and needs no exchange-rate service. Refusing unknown
  fields catches typos and a key pasted into the wrong file.
- **Alternatives:** Prices from LiteLLM's bundled list or from the provider's
  API at startup (network at startup, and a silent change of what a cap
  means); caps in environment variables; prices already converted to euros.
