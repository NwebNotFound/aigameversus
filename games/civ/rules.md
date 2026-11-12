# Throne of Tokens: rules

You lead one of 4–6 nations on a hex map. Alliances help; every alliance can be
broken.

## Map

You see tiles within 2 of your cities and armies; the rest is fog. Rumours from
others may be lies.

| Terrain | Yield / round | Move cost | Defense |
| --- | --- | --- | --- |
| plains | 2 food | 1 | — |
| forest | 2 wood | 2 | +25 % |
| hills | 1 iron, 1 food | 2 | +50 % |
| iron_deposit (rare) | 3 iron | 2 | +25 % |
| gold_vein (rare) | 3 gold | 2 | — |
| river | 1 food, 1 gold | 1, +1 to cross | attackers −25 % |
| mountains, water | — | impassable | — |

Iron is scarce, and every nation's start region is short of one resource.

## Cities

You start with a capital, 1 spearman, 1 settler and a stock of 5 food, 5 wood
and 5 gold. All your cities fill that one stock, and everything is paid from it.

A city yields 2 food, 1 wood and 1 gold, plus the tiles within 1 of it (within
2 from population 5). A tile feeds one city: the nearest, or the older of two
equally near. The tile under a city yields nothing. Each population eats
1 food and adds 1 of the city focus resource: growth = food, production = wood,
military = iron. Food a city makes beyond what its own population eats also
counts towards its growth: every 10 collected add 1 population, at most 1 per
round.

A city has 3 + population ÷ 2 building slots, at most 8, and one of each
building.

| Building | Cost | Effect |
| --- | --- | --- |
| farm | 4 wood | +2 food |
| sawmill | 3 wood, 1 gold | +2 wood |
| mine | 5 wood | +2 iron; city must border hills or iron |
| market | 4 wood, 3 gold | +3 gold, trade fee −50 % |
| barracks | 5 wood, 2 iron | needed for most units, training −20 % |
| wall | 6 wood, 3 iron | city defense +50 % |
| forge | 4 iron, 3 gold | units trained here +1 strength |
| granary | 5 wood | unpaid upkeep costs units 2 rounds later |
| watchtower | 3 wood, 1 iron | city vision +2 |

A building is paid when you order it, takes its slot at once and works from
the next round. Demolishing a finished building refunds 50 % of its cost,
rounded down.

## Units

| Unit | Cost | Str | Move | Upkeep | Notes |
| --- | --- | --- | --- | --- | --- |
| spearman | 2 wood, 1 food | 3 | 1 | 1 food | ×2 vs horseman, any city |
| swordsman | 3 iron, 1 food | 4 | 1 | 1 food | ×2 vs spearman |
| horseman | 3 iron, 2 food, 2 gold | 4 | 3 | 2 food | ×2 vs swordsman |
| archer | 3 wood, 1 iron | 2 | 1 | 1 food | ranged, fires first, +50 % in cities |
| siege_engine | 6 wood, 3 iron | 2 | 1 | 1 food, 1 gold | ×3 vs walls |
| settler | 6 food, 2 wood | 0 | 1 | 1 food | founds a city, any city |
| scout | 2 food, 1 gold | 1 | 3 | — | vision +2, flees, any city |

Units without "any city" need a barracks in the city that trains them. One
order trains 1 to 10 units of a kind; they are paid at once and stand in the
city as a new army. A barracks takes 20 % off the whole order, rounded up.

An army is a stack of up to 10 units on one tile. You can split units off as
a new army, merge armies that stand on one tile, and disband an army. An army
moves once per round and is as fast as its slowest unit. Entering a tile
costs its move cost, leaving a river 1 more; an army with points left may
always take one more step, so every army gets at least one tile far.
Mountains and water cannot be entered.

A settler founds a city on the tile where its army stands and is used up. The
tile must be at least 2 steps from every other city.

Upkeep is paid every round after your population has eaten. In a round in
which you cannot pay it in full you lose a random unit. A granary covers the
first 2 such rounds in a row; several granaries do not add up.

## Combat

Power = sum of strength × counter × (1 + terrain + wall + fortify) × random
0.8–1.2. Archers fire one round first, then melee. Higher power wins; the
loser loses units in proportion, the winner loses (loser ÷ winner power) × 40 %.
An army that did not move for a round is fortified: +25 % defense. Beating an
undefended city captures it with its buildings, −1 population; losing your
capital costs 20 % production for 5 rounds. Pillage destroys a building and
yields 50 % of its cost. Each round at war costs 2 % production, up to 30 %.

## Diplomacy

Treaties: peace, non_aggression (3–30 rounds), alliance (shared vision, joint
war, open borders), open_borders (3–30 rounds), tribute (1–20 rounds).
Reputation runs 0–100, starting at 50. Breaking a treaty costs 20 and everyone
sees it. Trades carry a 10 % fee, +10 % if your reputation is below 30.

## Orders

You submit all orders of a round in one `submit_orders` call, a list of orders
(at most 40; at most 3 messages and 3 treaty or trade offers). Diplomacy
orders run first, then cities, then armies; within each type the nations go
in seat order. An illegal order is dropped with a reason you read next round
(`refused`), and the rest still run. `legal` in your situation lists what you
can build and train, and `legal.orders` which order types can do something
now. `plan` (optional, at most 60 words) is a note to yourself: you get it
back next round as `your_plan_from_last_round`; nobody else reads it.

Example (your cities are `c1`, `c2`, your armies `a1`, `a2`):

```json
{"orders": [
  {"type": "focus", "city": "c1", "focus": "production"},
  {"type": "build", "city": "c1", "building": "farm"},
  {"type": "train", "city": "c1", "unit": "spearman", "count": 2},
  {"type": "settle", "army": "a2"},
  {"type": "move", "army": "a1", "to": [4, 3]}
], "plan": "Grow c1, settle east, keep a1 near the river."}
```

| Order | Arguments |
| --- | --- |
| build, demolish | city, building |
| focus | city, focus (growth, production, military) |
| train | city, unit, count (1 to 10) |
| move | army, to ([col, row], a tile in its `reachable`; a tile held by a nation you are at war with, or by barbarians, is attacked) |
| settle | army (its settler founds a city here) |
| split | army, units (unit ids to take out as a new army) |
| merge | armies (ids on one tile; they join the first) |
| disband | army |
| fortify | army (stays put; +25 % defense from next round) |
| pillage | army (destroys the newest building of an enemy city next to it) |
| message | to (nation or null for everyone), text (at most 60 words) |
| propose_treaty | to, kind, rounds (a tribute also: payer, payment) |
| respond | offer (id), accept (true/false) |
| declare_war, break_treaty | on (nation) / treaty (id) |
| propose_trade | to, gives, wants, rounds |

## A round

1. Everyone gets their situation and answers with one `submit_orders` at the
   same time. An offer made this round can be answered next round.
2. Resolution: your orders (diplomacy, cities, armies), barbarians, combat,
   tributes and trades, production and upkeep, growth, random events, war
   weariness, victory.

Random events: plague, drought, rebellion of recently conquered cities,
barbarians, gold finds, good harvests.

## Victory

- Domination: control 50 % of all cities.
- Economy: hold 500 gold for 5 rounds in a row; everyone sees the countdown.
- After round 60, highest score wins: cities × 10 + population + gold ÷ 10 +
  reputation ÷ 5.
