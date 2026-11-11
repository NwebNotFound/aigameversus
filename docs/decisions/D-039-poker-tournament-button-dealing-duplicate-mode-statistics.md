# D-039 · Poker tournament: button, dealing, duplicate mode, statistics

- **Date:** 2026-11-11
- **Decision:**
  - Tournament defaults are settings: `starting_stack` 1000, `small_blind` 10
    (big blind double), `double_every` 10 hands, `hand_limit` 100. At the limit
    the bigger stack ranks higher; equal stacks share a rank.
  - The button moves to the next seat that still has chips (a simple moving
    button, no dead button). With two players the button posts the small blind
    and acts first before the flop, last after it. A blind a player cannot
    afford is posted all-in. No antes, no burn cards.
  - The deck is shuffled once per hand and logged for spectators only. Hole
    cards go out by seat position, two per seat, in seat order; the board takes
    the next cards. Duplicate mode (`duplicate: {deck_seed, rotation}`) shuffles
    from `deck_seed` instead of the match seed and rotates the seating by
    `rotation`, so a rematch with the next rotation deals the same cards to the
    same seats with different players in them (DESIGN.md "Fairness"). Pairing
    the rematches is the game master's job.
  - Players knocked out in the same hand rank by chips at the start of that
    hand; equal chips share a rank.
  - Opponent statistics in the observation: hands dealt, hands played
    voluntarily (a call or raise before the flop), raises, showdowns, and
    shown bluffs (made the last bet or raise of a hand that went to showdown
    and won nothing).
  - Like Liar's Deck: `table_talk` once per turn without ending it, at most
    40 words, words only as `message` events; no `think` tool, thoughts are
    the plain text of an answer. `render_spec` is a plain method, not part of
    the interface yet.
- **Why:** Standard tournament practice where the spec is silent; seat-based
  dealing is what makes duplicate rematches fair.
- **Alternatives:** dead-button rules; a random first button; dealing from the
  small blind; a fixed duplicate pairing inside one match.
