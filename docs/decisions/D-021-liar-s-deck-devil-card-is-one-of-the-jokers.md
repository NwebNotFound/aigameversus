# D-021 · Liar's Deck devil card is one of the jokers

- **Date:** 2026-11-11
- **Decision:** In the devil-card variant the devil card is one of the two jokers
  (`devil_card: {card: joker, count: 1, trigger: revealed_on_liar_call, effect:
  all_others_shoot}` in `games/liars_deck/variants/devil_card.yaml`). The deck
  stays at 20 cards. When a "Liar!" call reveals it, every living player
  except the one who played it (the caller included) shoots at the same time,
  and the normal shot of that round is skipped (`replaces_normal_shot: true`).
- **Why:** The spec says "one card is the devil card" without saying which. A
  joker keeps the deck size and the table-card rules unchanged.
- **Alternatives:** A 21st card; one king, queen or ace marked as devil.
