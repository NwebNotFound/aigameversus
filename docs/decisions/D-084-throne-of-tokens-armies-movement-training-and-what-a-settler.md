# D-084 · Throne of Tokens armies: movement, training, and what a settler may do

- **Date:** 2026-11-11
- **Decision:** An army is a list of units on a tile, with an id that is
  never used twice. Where the spec is silent:
  - **Movement.** An army has the movement points of its slowest unit.
    Entering a tile costs the tile's movement cost; leaving a river tile costs
    the crossing on top. An army with points left may always take one more
    step, and a tile that costs more than it has left ends its move. A move
    order names a tile the army can reach this round; the server picks the
    way that leaves the most points, the shorter of two equal ones. An order
    lasts one round, and an army moves once per round: it remembers the round
    of its last move, and so do units split off from it and an army it is
    merged into. Armies of different nations may pass each other and stand on
    one tile until combat (step 7.4) says what happens then.
  - **Training.** One order trains 1 to 10 units of one kind. They are paid at
    once and stand in the city at once, as a new army. Discounts (barracks)
    apply to the whole order and each resource is rounded up, so a single
    swordsman costs its full 3 iron and five cost 12. A forge marks the units
    trained in its city with +1 strength; units without strength (settlers)
    get no mark.
  - **Organising.** `split` names kinds and takes the first units of each
    kind; it must leave a unit behind. `merge` joins armies on one tile into
    the first named, up to 10 units. `disband` removes a whole army.
  - **Founding.** A settler founds a city on the tile where its army stands
    and is used up. The tile must be at least `city.min_distance` (2) steps
    from every other city, so no city stands in another's first ring.
  - **Hunger.** The units a hungry nation loses are drawn from all its units
    with the same chance each, from a random stream named by round and
    nation.
  - The state has a round number, set by the event `round_started`, and all
    events are applied through `games/civ/turn.py`, which replaces the
    per-module `apply_event` of the state decision.
- **Why:** With the spec's costs (forest and hills 2) and its units (most
  move 1), a rule without the free last step would lock most armies out of
  most of the map. Naming a tile within reach keeps a move something the
  server can check against what the player sees, and keeps orders from
  running on for rounds after the plan changed. Rounding a discount up means
  it can never make a unit free. New armies instead of joining a garrison
  keep `train` free of surprises about army sizes. Two steps between cities
  is what makes the "nearest city works the tile" rule safe for first rings.
- **Alternatives:** Movement points carried over or spent exactly (slow
  units could not enter forest); orders to far targets that persist (need
  path memory and a cancel order); training that takes a round like building
  (the spec gives building a time and units none); units with ids of their
  own (longer prompts for little gain; an army's units are told apart by
  kind); splitting by position in the army (models count badly).
