# Throne of Tokens: the interfaces between its parts

The plugin is built by several people at once: combat and the turn flow
(7.4, 7.6), diplomacy and random events (7.5), the random bot and the
observation (7.7), the hex board (UI). This page pins what they share, so each
part can be written and tested against it. The rules themselves are in
[DESIGN.md](DESIGN.md) ("Spiel 3") and the numbers in
`games/civ/data/balance.yaml`; where this page is more precise, it wins. A
change to anything here is a change to this file in the same pull request.

## One round, one call per nation

A match has one setting, `rounds` (1 to 60; default 60, the `round_limit` of
`victory.yaml`): the round-limit victory is checked after that round instead
(D-133). Everything that names the last round reads `victory.round_limit(state,
data)`.

A match of Throne of Tokens is played in **rounds**. Every round is one
engine turn in which all nations act at once (`turn_mode = simultaneous`):
each nation is asked once and answers with **one** call, `submit_orders`.
There is no separate info or diplomacy phase: everything a nation needs is in
its observation, and its messages, offers and answers travel in the same call.
An offer made in round *r* can be answered in round *r + 1* and lapses after
that. (DESIGN.md's info calls and two diplomacy passes would cost three to
ten calls per nation and round; one call keeps a 60-round match of six
nations at 360 calls.)

The plugin resolves the round in this fixed order, after every nation has
answered. Each step is a function with the signature
`step(state, data, ctx)` (or `(state, ctx)` where it needs no data) that
emits events:

| # | Step | Module | Owner |
| --- | --- | --- | --- |
| 1 | `turn.begin_round` | turn | Builder |
| 2 | `diplomacy.expire` | diplomacy | Heavy |
| 3 | `economy.finish_construction` | economy | done |
| 4 | the round's orders, in this order: diplomacy (messages, treaties, wars), cities, armies | turn | Builder |
| 5 | `neutrals.act` (barbarians; rebel cities do nothing) | neutrals | Builder |
| 6 | `combat.resolve` | combat | Builder |
| 7 | `diplomacy.settle` (tribute, trades) | diplomacy | Heavy |
| 8 | `economy.produce` | economy | done |
| 9 | `armies.starve` | armies | done |
| 10 | `economy.grow` | economy | done |
| 11 | `events.roll` | events | Heavy |
| 12 | `combat.weariness` | combat | Builder |
| 13 | `victory.check` (sets `state.victory`; the match is over then) | victory | Heavy (#120) |

`turn.open_round` runs steps 1 to 3 and `turn.close_round` steps 4 to 13. The
plugin opens round 1 in its setup; each engine turn then closes the round the
nations answered on and, unless the match is won, opens the next (D-130). A
nation is therefore always asked on an open round.

Orders of one kind run in the order the nations are listed in the state
(their seat order), so the log does not depend on who answered first. An
order that is no longer legal when its turn comes (the stock was spent by an
earlier order, the army was destroyed) is dropped with `order_refused`.

## The call: `submit_orders`

One tool, offered to every nation every round. Its JSON schema is the source
of truth (`games/civ/orders.py`): one flat order object with a `type` and
every field an order may have; what a type needs is checked when the order
runs (a missing field is an `order_refused`). This is its shape:

```json
{
  "orders": [
    {"type": "build", "city": "c1", "building": "barracks"},
    {"type": "demolish", "city": "c1", "building": "farm"},
    {"type": "train", "city": "c1", "unit": "spearman", "count": 2},
    {"type": "focus", "city": "c2", "focus": "military"},
    {"type": "move", "army": "a3", "to": [12, 7]},
    {"type": "fortify", "army": "a3"},
    {"type": "pillage", "army": "a4"},
    {"type": "split", "army": "a3", "units": ["archer", "spearman"]},
    {"type": "merge", "armies": ["a3", "a5"]},
    {"type": "disband", "army": "a6"},
    {"type": "settle", "army": "a7"},
    {"type": "message", "to": "p2", "text": "Peace?"},
    {"type": "propose_treaty", "to": "p2", "kind": "non_aggression", "rounds": 10},
    {"type": "respond", "offer": "o4", "accept": true},
    {"type": "declare_war", "on": "p3"},
    {"type": "break_treaty", "treaty": "t2"},
    {"type": "propose_trade", "to": "p2", "gives": {"wood": 5}, "wants": {"gold": 3}, "rounds": 1}
  ],
  "plan": "Hold the river with a3; settle north next round."
}
```

- `orders` may be empty (a nation that does nothing). At most 40 orders, of
  them at most 3 `message` and at most 3 `propose_treaty` / `propose_trade`
  together; a `message` text has at most 60 words. The schema caps the
  list; the plugin drops every message and offer beyond those numbers, and
  a longer text, with `order_refused`.
- `plan` (optional, and only in a match with the setting `private_plan: "on"`, D-135;
  the field is absent from the tool otherwise) is the nation's own short plan, cut to its first 60
  words. Only that nation reads it again: as `your_plan_from_last_round` in
  its next observation (`plan_set`, private). It is kept in the state, never
  shown to another nation, and spectators see it.
- `to` and tiles are `[col, row]` (`games/civ/world.py`: odd rows sit half a tile
  to the right).
- `message` with `"to": null` is public; otherwise private to sender and
  receiver. Its text becomes the engine's `message` event, so other models
  read it as player content.
- The runner adds `thought` to the call as for every game.

**All nations at once.** The engine asks every nation of a round at the same
time (`TurnMode.SIMULTANEOUS`); their calls go through the match's one
`Budget`, whose ledger lock books them one after another. A nation whose
call fails, times out, or is refused after the corrections gets the game's
`random_action` for that round, as in every game (a few random legal
orders, `action_fallback` and `decision` in the log), and the round is
resolved for everyone as usual. A nation whose agent gave up plays random
orders from then on.

**What the engine refuses and what the plugin drops.** The engine checks the
call against the schema: a wrong shape is refused and the model corrects it,
as in every game. The plugin's `validate` refuses only a call it cannot read
at all. A single order that breaks a rule (not enough wood, not their
city, an army that already moved) is **dropped** when it runs, with an
`order_refused` event that only that nation sees, and the rest of the
orders go on. The nation reads the refusals at the top of its next
observation. A list of twenty orders is never thrown away for one mistake.

## Moving and fighting

- `move` walks the army along its shortest path within its movement
  (`armies.reachable`). If the target tile holds an army or a city of a
  nation it is **at war with**, or of `NEUTRAL`, the move is an **attack**:
  the army stops on the last free tile of its path and fights for the target
  in `combat.resolve`. Moving onto a tile of a nation it is not at war with
  is refused (`order_refused`). This holds for tiles in the nation's sight
  (`combat.sight`); a move onto a held tile out of sight stops on the tile
  before it and is refused, so the fog is found out only by spending the
  move. An attack needs its target in sight, and every unseen tile gets the
  same refusal (D-126).
- Being at war: `diplomacy.at_war(state, a, b)`, or either side is
  `NEUTRAL`. War is entered only through `declare_war`, which is never
  refused for a treaty: it ends every treaty between the two, each counted as
  broken (−20 reputation, public). `diplomacy.may_attack(state, a, b)` tells
  whether a treaty forbids attacking; `declare_war` uses it to decide which
  allies of the target join.
- Combat (7.4) follows DESIGN.md's formula with the numbers of `balance.yaml`:
  power = Σ strength × counter × (1 + terrain + walls + fortified) ×
  random(0.8–1.2), archers fire one ranged round first, the loser loses units
  in proportion to the power ratio, the winner loses (loser ÷ winner) × 40 %.
  The random factor comes from `ctx.rng("combat", round, battle_index)`.
- An attacker that wins against a city with no defending army conquers it
  (`city_conquered`): owner changes, population −1, buildings kept,
  `City.conquered_round` set; a conquered capital costs its old owner 20 %
  production for 5 rounds.
- `fortify` applies from the next round if the army does not move.
  `pillage` destroys the newest building of a foreign city the army stands
  next to (at war) and gains half its cost as loot.
- War weariness: every round at war (`len(diplomacy.wars_of(state, nation))`
  > 0) lowers production by 2 %, at most 30 %, back to 0 in peace.

## State (`games/civ/state.py`)

What exists stays as it is (`round`, `world`, `nations`, `cities`, `armies`,
`armies_raised`). Additions, each by the step that owns it:

| Field | Type | Owner |
| --- | --- | --- |
| `NEUTRAL = "neutral"` | owner id of barbarians and rebel cities | Builder / Heavy |
| `Nation.reputation` | `int`, 50 at start, 0–100 | Heavy |
| (capital) | the city on the nation's start tile, whoever holds it (`combat.capital`) | Builder |
| `Nation.weary_rounds` | rounds in a row at war | Builder |
| `Nation.capital_lost_until` | round or `None` | Builder |
| `City.conquered_round` | `int` or `None` | Builder (set), Heavy (read) |
| (walls) | a city has walls when `"wall"` is in its `buildings` | data |
| `Army.fortified_from` | round or `None` | Builder |
| `CivState.attacks` | this round's attacks `{army, target}`, until fought | Builder |
| `CivState.treaties`, `offers`, `deals`, `wars`, `conditions`, `rich_rounds` | see #105, #120 | Heavy |
| `CivState.victory` | `{kind, winners, placements}` or `None` (`is_over` reads it) | Heavy (#120) |
| `Nation.plan` | the last `plan` the nation sent, at most 60 words | Builder |
| `CivState.refused` | dropped orders `{nation, round, order, reason}` of this and the last round | Builder |
| `CivState.battles` | battles `{round, tile, winner, nations}` of this and the last round, for the board | Builder |

Every field must survive a JSON round trip (lists, not tuples).

## Events

Game events, each with the nations that may see it (`visible_to`). Existing
events of `economy.py` and `armies.py` keep their names and data.

| Event | Data | Seen by |
| --- | --- | --- |
| `round_started` | `round` | all |
| `map_drawn` | `rows` (terrain ids), `starts` | spectators only |
| `order_refused` | `nation, round, order, reason` | that nation |
| `plan_set` | `nation, plan` | that nation |
| `battle` | `tile, attacker {nation, army, power, lost}, defender {nation, army or city, power, lost}, winner` | both sides |
| `city_conquered` | `city, from, to, round` | all |
| `city_pillaged` | `city, army, building, loot` | both sides |
| `army_fortified` | `army` | owner |
| `war_weariness` | `nation, modifier` | that nation |
| `victory` | `kind` (`domination` / `economy` / `round_limit`), `winners, round, standings, placements` | all |
| diplomacy and event types | as in #105 | as in #105 |

A battle is seen by both sides only; what others learn of it comes from their
fog view of the tile. Conquest is announced to everyone: the map changes
hands, and viewers need the moment.

## Observation of a nation (built in 7.7, #119)

`get_observation(state, nation)` (`games/civ/observation.py`, `observe`)
returns only what that nation may know, built from its fog view
(`fog.map_view`), never from the map:

- `round`, `rounds_total`, `you`,
- `victory`: the nation's standing in every win condition, so a model need
  not compute it: `domination` (its share of all cities, the share needed),
  `economy` (gold held, rounds held, the public countdown of any nation
  close to it), `score` (its own score by the round-limit formula; no rank,
  because another nation's score holds its gold), and
  `closest_win` (the condition it is nearest to),
- `stock`, `reputation`, `production_modifier` (weariness, lost capital),
- `cities` (own, full) and `armies` (own, with `reachable` tiles and
  `can_settle`),
- `seen` (foreign cities and armies on visible tiles: owner, strength,
  units), `map` (the fog view, compact),
- `relations` (treaties, wars, and whom it is at war with), `offers` (to
  answer this round), `refused` (own dropped orders of last round). Messages
  and the nation's other events of last round reach the model as the
  prompt's events, where another model's words are marked as player content;
  they are not copied into the observation (D-130), so `messages` and
  `last_round` stay empty,
- `legal`: what is possible now, so a model need not guess: per city what it
  may build (with the cost) and train (with the most it can pay for), the
  unit costs, and `orders`, the order types that can do something this round,
  each with its fields and, where only some qualify, which cities, armies,
  offers or nations (e.g. `move` only when an army can move),
- `your_plan_from_last_round`: the `plan` the nation sent last round, or `null`,
- `scoreboard` (below), added by the plugin.

**Public by rule (D-128).** Public: the total number of cities in the world,
the city count per nation, and who holds the gold countdown (and how far it
is); also reputations, treaties and wars. Private: other nations' scores
(they hold gold and population), stocks,
positions, buildings, and armies outside the nation's own sight. The
observation carries the public part in one field, built by the plugin from
the state and nothing else, so no number is derived from fogged state by
accident:

```json
"scoreboard": {
  "round": 12,
  "cities_total": 12,
  "cities": {"p1": 3, "p2": 5, "p3": 4},
  "domination_needed": 6,
  "gold_countdown": {"nation": "p2", "rounds_held": 2, "rounds_needed": 5},
  "reputation": {"p1": 50, "p2": 30, "p3": 55}
}
```

`round` is the round being played. `gold_countdown` is `null` while nobody
holds enough gold; with several holders it names the one closest to winning. Everything else in
an observation about another nation comes from its fog view.

**Public by rule (D-128).** Public: the total number of cities in the world,
the city count per nation, and who holds the gold countdown (and how far it
is); also reputations, treaties and wars. Private: other nations' scores
(they hold gold and population), stocks,
positions, buildings, and armies outside the nation's own sight. The
observation carries the public part in one field, built by the plugin from
the state and nothing else, so no number is derived from fogged state by
accident:

```json
"scoreboard": {
  "round": 12,
  "cities_total": 12,
  "cities": {"p1": 3, "p2": 5, "p3": 4},
  "domination_needed": 6,
  "gold_countdown": {"nation": "p2", "rounds_held": 2, "rounds_needed": 5},
  "reputation": {"p1": 50, "p2": 30, "p3": 55}
}
```

`round` is the round being played. `gold_countdown` is `null` while nobody
holds enough gold; with several holders it names the one closest to winning. Everything else in
an observation about another nation comes from its fog view.

**Size budget.** An observation and its prompt are what every call pays
for: 360 calls in a 60-round match of six nations. An observation stays under
5,000 tokens (17,500 bytes of JSON, counted as the estimate counts: bytes /
3.5), and a plugin test fails on any observation of a 60-round bot match of
six nations above it. With cheap models (about 0.10 USD per million input
tokens) the observations of such a match cost about 0.18 USD. A strong model
can pass the match cap of 0.50 EUR: `POST /matches/estimate` works for every
plugin and must be asked before any Civ run with models, and a run above the
cap needs its own explicit budget.

`situation_summary` (p2) is built from this observation only.

## Board for spectators: `render_spec`

```json
{
  "layout": "hex_map",
  "round": 12,
  "rounds_total": 60,
  "cols": 24,
  "rows": 16,
  "terrain": ["ppfh..", "..."],
  "legend": {"p": "plains", "f": "forest", "h": "hills", "i": "iron_deposit", "g": "gold_vein", "r": "river", "m": "mountains", "w": "water"},
  "cities": [{"id": "c1", "owner": "p1", "tile": [3, 4], "population": 4, "capital": true, "walls": false}],
  "armies": [{"id": "a2", "owner": "p2", "tile": [5, 4], "strength": 11, "units": {"spearman": 2, "archer": 1}, "fortified": false}],
  "nations": [{"id": "p1", "stock": {"food": 12, "wood": 5, "iron": 2, "gold": 30}, "reputation": 50, "cities": 3, "at_war": ["p2"]}],
  "treaties": [{"kind": "alliance", "parties": ["p1", "p3"]}],
  "wars": [["p1", "p2"]],
  "fog": {"p1": ["0011..", "..."]},
  "battles": [{"tile": [5, 4], "winner": "p2"}]
}
```

`terrain` is one string per row, one letter per tile (`legend` maps every letter to a terrain id of `terrain.yaml`);
`fog` is one string per row per nation (`1` = seen this round). `battles` are
those of the round resolved last: `{round, tile, winner, nations}`.

**This full board is for the Spectator view only.** The spoiler-free view
shows the board as **one nation** sees it (the viewer picks it; the first in
seat order by default): the plugin's `render_spec_for(state, nation)`, built
on the server (`GET /matches/{id}/board?nation=p1`), keeps only

- `layout`, `round`, `rounds_total`, `cols`, `rows`, `terrain`, `legend`
  (the land itself is no secret),
- the cities and armies on tiles that nation sees this round, with `id`,
  `owner`, `tile`, `population`, `capital`, `walls` for a city and `id`,
  `owner`, `tile`, `strength` for an army (unit lists only for its own),
- `nations` with `id`, `reputation`, `cities` and `at_war` (stock only for
  its own), `treaties` and `wars` (public), its own `fog` row set, and the
  `battles` it fought or saw.

Every other field is dropped, and an unknown field is never passed on: the
allowlist for `hex_map` in `web/src/lib/server/redact.ts` mirrors this list.
"All nations" at once exists only in the Spectator view.

## Random bot (7.7)

`random_action(observation, tools, rng)` returns a `submit_orders` with a few
legal orders built from `legal` and `armies[].reachable` only; a random bot
never needs the state.
