# D-018 · The bluff card game is called Liar's Deck

- **Date:** 2026-11-11
- **Decision:** The game's public name is "Liar's Deck" everywhere: README, UI,
  docs, and the game id (`liars_deck`, package `games/liars_deck/`). The spec
  used the title of the commercial game that inspired it as a working title;
  `docs/DESIGN.md` was edited to the new name. Code refers to the game by its
  id, and the display name is defined in exactly one place, so a later rename
  is a one-line change.
- **Why:** Decided by the project owner. The project carries no title,
  characters or assets of an existing game.
- **Alternatives:** Keeping the working title; a different title, which
  remains possible because of the single definition.
