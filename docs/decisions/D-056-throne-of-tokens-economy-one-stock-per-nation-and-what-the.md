# D-056 · Throne of Tokens economy: one stock per nation, and what the spec leaves open about cities

- **Date:** 2026-11-11
- **Decision:** A nation has one stock of food, wood, iron and gold. Its
  cities fill it and everything is paid from it. Where the spec is silent:
  - **Tiles.** A city works the tiles around it, not the one it stands on;
    the city's own yield (2 food, 1 wood, 1 gold) stands for that tile. A tile
    feeds one city: the nearest that reaches it, the older of two equally
    near. So a city's first ring can only be taken by building on it.
  - **Growth.** The food a city makes beyond what its own population eats
    goes to the stock and also counts towards that city's growth. At 10
    collected the city gains a population and keeps the rest, at most one
    population per round. A city that eats more than it makes takes the
    difference from the stock and collects nothing; nobody starves in a city.
  - **Buildings.** An order is paid at once and takes a slot at once; the
    building works from the next round (`build_rounds` rounds later). Only a
    finished building can be demolished; the refund is rounded down per
    resource. A city that loses population keeps buildings beyond its slots.
  - **Upkeep.** After the yields are in, the population eats, then the units
    take their upkeep. What the stock cannot cover is not paid and the stock
    ends at 0. A round with upkeep not paid in full, in food or gold, is a
    hungry round and costs a random unit; a granary covers the first two
    hungry rounds in a row. Only the nation's best granary counts.
  - **Sight.** A finished watchtower adds its bonus to the sight of its city.
  - Shares of an amount are computed in decimal and rounded down, so 29 % of
    100 is 29 whatever binary fractions make of it.
- **Why:** The spec prices units and trades in food and counts gold per
  nation, so resources cannot belong to cities; but it lets a city grow on
  its own surplus. Counting the surplus twice is the reading that needs no
  rule for sharing food between growth, units and trade, and it is the one
  sentence a model has to remember. Nearest-city tiles need no stored borders
  and never surprise the owner of a ring. Gold upkeep counts like food so
  that a siege engine is not free for a nation without gold. Granaries that
  added up would let a large nation keep an unpaid army for many rounds.
- **Known consequence, for balancing:** on the growth focus a population pays
  for itself, so a capital gains a population almost every round (about 60
  after 60 rounds on the shipped map, against 12 to 18 on the other two
  focuses, where growth levels off). Population counts in the final score.
  `city.growth_food` in `balance.yaml` is the number to raise if bot matches
  show that this decides games.
- **Alternatives:** Growth that uses up the food (units and settlers would
  compete with automatic growth for the same stock, and the player could not
  steer it); a stock per city (needs transport rules); tiles assigned to the
  city founded first (an old city growing to radius 2 would take a
  neighbour's first ring); the city tile also yielding (the map's start
  regions are balanced for six worked tiles); losing population when a city
  cannot be fed (a second starvation rule next to the one for units).
