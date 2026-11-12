# D-029 · A game's title and rules text each live in one place

- **Date:** 2026-11-11
- **Decision:** `GamePlugin.name` is the title that prompts, and later the UI,
  show; code never writes a title anywhere else. This is the "exactly one
  place" of D-018. `GamePlugin.rules()` returns the game's `rules.md`. The
  prompt puts the `name` above the rules, so a rules text does not need the
  title. The rules texts written before their plugins (Liar's Deck, Poker,
  Werewolf, Throne of Tokens) still open with a title heading; it goes when
  each game gets its plugin.
- **Why:** A rename is then a one-line change, and the rules text a model
  reads is a file that people can read and review too.
- **Alternatives:** The title as the heading of `rules.md`; rules as a string
  in the plugin.
