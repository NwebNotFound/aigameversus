# Throne of Tokens data

All content of the strategy game lives here as YAML. Code reads it through
`games/civ/data_loader.py`, which validates every file at startup and stops
with an error naming the file, the entry and the problem.

| File | Holds |
| --- | --- |
| `terrain.yaml` | tile yields, movement cost, defense, river rules |
| `buildings.yaml` | buildings and their effects; build time and demolish refund |
| `units.yaml` | units: cost, strength, movement, upkeep, counters, where they train |
| `events/<id>.yaml` | one random event per file |
| `treaties.yaml` | treaty types and reputation |
| `victory.yaml` | victory conditions and the round-limit score |
| `balance.yaml` | every other tuning number: start, cities, armies, combat, trade, turn |
| `*.schema.json` | JSON schemas, generated from the loader's models |

Conventions: ids are `snake_case` English and never change once used (replays
refer to them). Every entry has an English `name` and a German `name_de`.
Resources are `food`, `wood`, `iron`, `gold`. Modifiers are relative:
`0.25` = +25 %, `-0.2` = −20 %.

Check your change:

```bash
uv run python -m games.civ.data_loader   # prints "ok" or the problems
uv run pytest games/civ
```

Editors with the YAML language server pick up the schema from the first line of
each file and show errors as you type.

## Add a unit

Append an entry to `units.yaml`:

```yaml
  - id: pikeman
    name: Pikeman
    name_de: Pikenier
    cost: {wood: 3, iron: 1}
    strength: 4
    movement: 1
    upkeep: {food: 1}
    counters: [{target: horseman, multiplier: 2}]
    trained_in: barracks   # a building id, or null for any city
```

Optional flags (`ranged`, `first_strike`, `city_defense`, `vs_walls_multiplier`,
`founds_city`, `vision_bonus`, `auto_retreat`) default to off. `counters` and
`trained_in` must name existing ids.

## Add a building

Append to `buildings.yaml` with `cost` and `effects`. Available effects:
`yields`, `trade_fee_modifier`, `training_cost_modifier`, `city_defense`,
`trained_unit_strength_bonus`, `famine_delay_rounds`, `vision_bonus`.
`requires_adjacent_terrain` lists terrain ids the city must border.

## Add an event

Create `events/<id>.yaml`; the file name must equal the `id`. Set
`probability_per_round` (0–1), a `target` (`city`, `region` with
`region_radius`, `nation` or `map`), optional `duration_rounds` and
`only_conquered_within_rounds`, and at least one effect:
`population_change`, `yield_modifiers`, `resources`, `city_becomes_neutral`,
`spawn_neutral_army`.

## Something the fields cannot express

A new kind of effect needs code: add the field to the model in
`data_loader.py`, implement it in the matching system under `games/civ/systems/`,
then regenerate the schemas:

```bash
uv run python -m games.civ.data_loader --write-schemas
```

A test fails while the committed schemas are out of date.

## Mods (planned, not built yet)

The plan for `mods/`, so content can change without touching these files:

- A mod is a folder `mods/<mod_id>/` with a `mod.yaml` (id, name, version) and
  the same layout as this folder under `games/civ/data/`.
- A match lists the mods it uses, in order; none are on by default.
- Merge rules, applied in that order on top of this folder:
  - list files (`terrain`, `buildings`, `units`, `treaties`): an entry with a
    known id replaces that entry whole; a new id is added; `remove: [ids]` deletes;
  - `events/<id>.yaml`: a file with the same name replaces the event, a new
    name adds one;
  - `balance.yaml`, `victory.yaml` and the `rules`/`reputation` blocks: deep
    merge, the mod's keys win.
- The merged result goes through the same validation and reference checks, so
  a mod that removes a unit still used elsewhere fails with the usual message.
- Each match stores its mod list and a hash of the merged data, so a replay
  can tell when the rules it was played with have changed.
