# D-033 · Liar's Deck engine: turns, talk, thoughts and open rules

- **Date:** 2026-11-11
- **Decision:**
  - Card ids name the rank (`K1`-`K6`, `Q1`-`Q6`, `A1`-`A6`, `J1`, `J2`); in
    the devil-card variant the devil joker is `DV` and its holder sees it.
    Other players never see ids of unrevealed cards.
  - Each revolver is loaded once per match (live chamber by seed, spectators
    only) and is not reset between rounds, so the risk keeps rising.
  - The first round starts with the first seat. After a call, the next round
    starts with the player who pulled the trigger if alive, otherwise with the
    other side of that call; after a devil card, with its player.
  - `table_talk` does not end the turn and is allowed once per turn; every
    text (talk, claim, call) has at most 40 words. Words go out only as
    `message` events.
  - There is no `think` tool: private thoughts are the plain text of a
    model's answer, which the engine's thoughts channel already logs for
    spectators only. `rules.md` says so.
  - "Only one player holds cards" makes that player call automatically. A
    play that leaves no other holder is checked by the next living player;
    normal play cannot reach this, it is a safeguard.
  - `render_spec(state)` exists on the plugin as a plain method (a card-table
    layout with every hand, never the live chambers) and is not added to the
    `GamePlugin` interface until the UI defines it (see D-009).
- **Why:** The spec leaves these open; each choice keeps one action per turn,
  keeps hidden information out of other players' views and reuses the
  engine's existing channels instead of adding parallel ones.
- **Alternatives:** talk as part of every action only; a `think` tool that
  emits a spectator-only event; reloading revolvers each round; a random
  first starter.
