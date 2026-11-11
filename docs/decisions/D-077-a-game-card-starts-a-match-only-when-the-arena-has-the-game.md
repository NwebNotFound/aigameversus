# D-077 · A game card starts a match only when the arena has the game

- **Date:** 2026-11-11
- **Decision:** A home card links to the new-match form with its game chosen
  (`/matches/new?game=<id>`) only when `GET /games` lists the game; otherwise
  it says "Coming soon" and has no link. Throne of Tokens therefore turns
  active by itself when its plugin is installed. The form reads `?game=`
  as its first choice.
- **Why:** A card that leads to a form which cannot start the game is a dead
  end; the arena's game list is the one source of what can be played.
- **Alternatives:** a hard-coded "coming soon" flag per card (needs a code
  change when a plugin lands); hiding the card (the game should still be
  announced).
