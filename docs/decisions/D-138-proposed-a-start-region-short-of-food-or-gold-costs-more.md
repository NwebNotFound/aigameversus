# D-138 · A start region short of food or gold costs more than one short of iron or wood

- **Date:** 2026-11-12
- **Status:** accepted by the lead on 2026-11-12, in force from Throne of Tokens
  version 2 (`CivGame.version`, recorded in `match_started`).
- **Decision:** A food-short region gets one plains instead of one forest:
  `food: [plains, forest, hills, hills, river, river]`. Its region now yields as
  much food as a gold- or iron-short one (6) and less only than a wood-short one
  (8), so "short of food" is the mildest shortage; a version with 5 food (one
  plains for a hills and a river) kept it strictly short but changed nothing
  measurable (2.65 against 2.64). Every nation's start region is short of one resource
  (`balance.yaml`, `map.start_regions`), but the four shortages do not cost the
  same. Over 80 seeds, nations short of food or gold rank 0.4 to 1.0 places
  worse than those short of iron or wood, at every table size (for example
  four nations, 60 rounds: food 2.69, gold 2.71, iron 2.27, wood 2.21). The six
  tiles around a capital yield 4 food for a food-short region, 6 for gold- and
  iron-short and 8 for wood-short ones; a gold-short region has no gold tile at
  all. Food drives growth, settlers and upkeep, and the round-limit score counts
  population and gold, so those two shortages cost score directly.
- **Why:** In memory, on the same seeds, food-short nations move from 2.64 to 2.33 (four
  nations, 20 rounds) and from 3.30 to 3.06 (five nations); with six nations the
  gap stays (3.92 to 3.79).
- **Open:** a river instead of one hills for gold-short regions changed nothing
  measurable (2.85 to 2.81), so no gold change is proposed yet. The gold gap may
  come from the score formula (gold ÷ 10) rather than the tiles; models may also
  spend gold better than random bots. Worth a look once real Civ matches exist.
- **Alternatives:** A start bonus of the scarce resource (needs code and a new
  number); leave it and rotate start positions in experiments (C1 already
  rotates, which evens it out across a design but not within one match).
