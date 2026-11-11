# D-010 · Named random streams derived from the seed

- **Date:** 2026-11-11
- **Decision:** A plugin gets randomness from `ctx.rng(*key)`, a stream derived
  from the match seed and the key by SHA-256. A key may be used once per match.
  Random bots and the engine fallback use separate streams.
- **Why:** A stream depends only on seed and key, so a match can continue from
  its log without saved generator state, rejected attempts and bot draws cannot
  shift the game's randomness, and a game can deal the same cards again on
  purpose (duplicate poker: key by hand number).
- **Alternatives:** One generator for the whole match (its state must be saved
  to resume, and any extra draw changes everything after it).
