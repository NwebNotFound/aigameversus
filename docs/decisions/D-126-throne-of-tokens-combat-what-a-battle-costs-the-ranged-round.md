# D-126 · Throne of Tokens combat: what a battle costs, the ranged round, and which city is a capital

- **Date:** 2026-11-12
- **Decision:** Combat (`games/civ/combat.py`) follows DESIGN.md's power
  formula with the numbers of `balance.yaml`, and fills in what the spec
  leaves open:
  - A counter works by the share of enemy units it counters: a swordsman
    against an army that is half spearmen is 1.5 times as strong.
  - The loser of a battle loses (winner power ÷ loser power) × 0.5 of its
    units, at least one; the winner loses (loser ÷ winner) × 40 %
    (`winner_loss_factor`). A tie holds the tile.
  - Archers fire one ranged round first: each side loses (the other side's
    ranged power ÷ its own power) × 0.5 of its units.
  - Which units fall is drawn from `ctx.rng("combat", round, battle)`.
  - An attacker that wins against a tile with no army left takes it; a city
    on it changes hands (`city_conquered`, public). A nation's capital is the
    city on its start tile; losing it costs 20 % production for 5 rounds, war
    weariness 2 % per round at war, up to 30 %, both on the yields.
  - Attacks are ordered during the army orders and fought afterwards, in
    order; an attack whose army is gone or whose target is empty is called
    off.
- **Why:** The spec says the loser loses "in proportion to the power ratio"
  without a factor, and gives the ranged round no losses; 0.5 makes a battle
  of equals cost both sides about half, so wars wear armies down without
  wiping them out in one round. The start tile needs no new field and cannot
  be argued about.
- **Alternatives:** Full counter multiplier for any countered unit present
  (one spearman would double a whole army of swordsmen); the loser always
  wiped out (no retreat, no attrition); a capital flag in the state (one more
  thing a log must carry).
