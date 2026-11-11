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

You start with a capital, 1 spearman and 1 settler. A city yields 2 food,
1 wood and 1 gold, plus the tiles within 1 (within 2 from population 5). Every
10 surplus food adds 1 population. Each population eats 1 food and adds 1 of
the city focus resource: growth = food, production = wood, military = iron.
A city has 3 + population ÷ 2 building slots, at most 8.

| Building | Cost | Effect |
| --- | --- | --- |
| farm | 4 wood | +2 food |
| sawmill | 3 wood, 1 gold | +2 wood |
| mine | 5 wood | +2 iron; city must border hills or iron |
| market | 4 wood, 3 gold | +3 gold, trade fee −50 % |
| barracks | 5 wood, 2 iron | needed for most units, training −20 % |
| wall | 6 wood, 3 iron | city defense +50 % |
| forge | 4 iron, 3 gold | units trained here +1 strength |
| granary | 5 wood | famine hits 2 rounds later |
| watchtower | 3 wood, 1 iron | city vision +2 |

Building takes 1 round. Demolishing refunds 50 %.

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

Units without "any city" need a barracks. An army holds up to 10 units. If you
cannot pay food upkeep, you lose a random unit every round.

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

## A round

1. Info: up to 8 info tool calls.
2. Diplomacy: messages, treaties, trades; 2 passes.
3. Orders: everyone submits secretly with `submit_orders` at the same time.
4. Resolution: trade → build and train → movement → combat → production →
   growth → events.

Random events: plague, drought, rebellion of recently conquered cities,
barbarians, gold finds, good harvests.

## Victory

- Domination: control 50 % of all cities.
- Economy: hold 500 gold for 5 rounds in a row; everyone sees the countdown.
- After round 60, highest score wins: cities × 10 + population + gold ÷ 10 +
  reputation ÷ 5.
