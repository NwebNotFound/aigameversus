# D-138 · Proposed: a start region short of food or gold costs more than one short of iron or wood

- **Date:** 2026-11-12
- **Status:** proposed, not in force. The rules are unchanged until the lead
  accepts this (research/civ-balance.md has the numbers).
- **Decision:** Proposed, not in force: give a food-short region one plains instead of one forest (below). Every nation's start region is short of one resource
  (`balance.yaml`, `map.start_regions`), but the four shortages do not cost the
  same. Over 80 seeds, nations short of food or gold rank 0.4 to 1.0 places
  worse than those short of iron or wood, at every table size (for example
  four nations, 60 rounds: food 2.69, gold 2.71, iron 2.27, wood 2.21). The six
  tiles around a capital yield 4 food for a food-short region, 6 for gold- and
  iron-short and 8 for wood-short ones; a gold-short region has no gold tile at
  all. Food drives growth, settlers and upkeep, and the round-limit score counts
  population and gold, so those two shortages cost score directly.
- **Why:** the change would be `food: [plains, forest, hills, hills, river, river]`.
  In memory, on the same seeds, food-short nations move from 2.64 to 2.33 (four
  nations, 20 rounds) and from 3.30 to 3.06 (five nations); with six nations the
  gap stays (3.92 to 3.79).
- **Open:** a river instead of one hills for gold-short regions changed nothing
  measurable (2.85 to 2.81), so no gold change is proposed yet. The gold gap may
  come from the score formula (gold ÷ 10) rather than the tiles; models may also
  spend gold better than random bots. Worth a look once real Civ matches exist.
- **Alternatives:** A start bonus of the scarce resource (needs code and a new
  number); leave it and rotate start positions in experiments (C1 already
  rotates, which evens it out across a design but not within one match).
