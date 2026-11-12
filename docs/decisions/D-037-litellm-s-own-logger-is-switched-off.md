# D-037 · LiteLLM's own logger is switched off

- **Date:** 2026-11-11
- **Decision:** `LiteLLMModel` disables the `LiteLLM` logger when it loads the
  library. The arena logs only the kind of a failure (D-026).
- **Why:** At debug level LiteLLM logs every request and every provider error
  text. Such a text can quote a key, and a request holds a player's private
  view of the game. A test runs a match at debug level with a provider error
  that quotes the key and finds neither in logs, output, events or the ledger.
- **Alternatives:** A filter that redacts known secrets from all log records
  (cannot know every secret, and prompts would still be logged); raising the
  logger's level only (any later `setLevel` brings the text back).
