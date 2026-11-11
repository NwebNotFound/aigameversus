import json
import shutil
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator

from games.civ.data_loader import DATA_DIR, CivDataError, json_schemas, load_civ_data


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    """A writable copy of the real data, for breaking on purpose."""
    copy = tmp_path / "data"
    shutil.copytree(DATA_DIR, copy)
    return copy


def edit(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    assert old in text, f"test setup: {old!r} not in {path.name}"
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def rejected(data_dir: Path) -> str:
    with pytest.raises(CivDataError) as info:
        load_civ_data(data_dir)
    return str(info.value)


def test_shipped_data_loads_with_all_content_from_the_spec():
    data = load_civ_data()

    assert set(data.terrain) == {
        "plains", "forest", "hills", "iron_deposit", "gold_vein", "river", "mountains", "water",
    }  # fmt: skip
    assert set(data.buildings) == {
        "farm", "sawmill", "mine", "market", "barracks", "wall", "forge", "granary", "watchtower",
    }  # fmt: skip
    assert set(data.units) == {
        "spearman", "swordsman", "horseman", "archer", "siege_engine", "settler", "scout",
    }  # fmt: skip
    assert set(data.events) == {
        "plague", "drought", "rebellion", "barbarians", "gold_find", "good_harvest",
    }  # fmt: skip
    assert set(data.treaties) == {"peace", "non_aggression", "alliance", "open_borders", "tribute"}


# The tables of DESIGN.md "Spiel 3", copied by hand: (cost, strength, movement, upkeep).
SPEC_UNITS = {
    "spearman": ({"wood": 2, "food": 1}, 3, 1, {"food": 1}),
    "swordsman": ({"iron": 3, "food": 1}, 4, 1, {"food": 1}),
    "horseman": ({"iron": 3, "food": 2, "gold": 2}, 4, 3, {"food": 2}),
    "archer": ({"wood": 3, "iron": 1}, 2, 1, {"food": 1}),
    "siege_engine": ({"wood": 6, "iron": 3}, 2, 1, {"food": 1, "gold": 1}),
    "settler": ({"food": 6, "wood": 2}, 0, 1, {"food": 1}),
    "scout": ({"food": 2, "gold": 1}, 1, 3, {}),
}
SPEC_BUILDING_COSTS = {
    "farm": {"wood": 4},
    "sawmill": {"wood": 3, "gold": 1},
    "mine": {"wood": 5},
    "market": {"wood": 4, "gold": 3},
    "barracks": {"wood": 5, "iron": 2},
    "wall": {"wood": 6, "iron": 3},
    "forge": {"iron": 4, "gold": 3},
    "granary": {"wood": 5},
    "watchtower": {"wood": 3, "iron": 1},
}
# (yields, movement cost, defense)
SPEC_TERRAIN = {
    "plains": ({"food": 2}, 1, 0.0),
    "forest": ({"wood": 2}, 2, 0.25),
    "hills": ({"iron": 1, "food": 1}, 2, 0.5),
    "iron_deposit": ({"iron": 3}, 2, 0.25),
    "gold_vein": ({"gold": 3}, 2, 0.0),
    "river": ({"food": 1, "gold": 1}, 1, 0.0),
    "mountains": ({}, None, 0.0),
    "water": ({}, None, 0.0),
}


@pytest.mark.parametrize("unit_id", SPEC_UNITS)
def test_every_unit_matches_the_spec_table(unit_id: str):
    unit = load_civ_data().units[unit_id]

    assert (unit.cost, unit.strength, unit.movement, unit.upkeep) == SPEC_UNITS[unit_id]


@pytest.mark.parametrize("building_id", SPEC_BUILDING_COSTS)
def test_every_building_cost_matches_the_spec_table(building_id: str):
    assert load_civ_data().buildings[building_id].cost == SPEC_BUILDING_COSTS[building_id]


@pytest.mark.parametrize("terrain_id", SPEC_TERRAIN)
def test_every_terrain_matches_the_spec_table(terrain_id: str):
    terrain = load_civ_data().terrain[terrain_id]

    assert (terrain.yields, terrain.movement_cost, terrain.defense) == SPEC_TERRAIN[terrain_id]


def test_spot_check_numbers_against_the_spec():
    data = load_civ_data()

    assert data.terrain["river"].crossing_extra_cost == 1
    assert data.terrain["river"].attacker_modifier == -0.25
    assert data.terrain["mountains"].movement_cost is None
    assert data.buildings["market"].cost == {"wood": 4, "gold": 3}
    assert data.buildings["mine"].requires_adjacent_terrain == ["hills", "iron_deposit"]
    assert data.units["horseman"].cost == {"iron": 3, "food": 2, "gold": 2}
    assert data.units["spearman"].trained_in is None
    assert data.units["swordsman"].trained_in == "barracks"
    assert data.reputation.break_treaty_penalty == -20
    assert data.victory.economy.gold == 500
    assert data.victory.round_limit.rounds == 60
    assert data.balance.city.building_slots.max == 8
    assert data.balance.war_weariness.max_production_modifier == -0.3


def test_every_entry_has_english_and_german_names():
    data = load_civ_data()
    groups = [data.terrain, data.buildings, data.units, data.events, data.treaties]

    for entry in (entry for group in groups for entry in group.values()):
        assert entry.name.strip() and entry.name_de.strip(), entry.id


def test_committed_json_schemas_match_the_models():
    for name, schema in json_schemas().items():
        committed = json.loads((DATA_DIR / name).read_text(encoding="utf-8"))
        assert committed == schema, (
            f"{name} is stale: run `uv run python -m games.civ.data_loader --write-schemas`"
        )


def test_yaml_files_pass_their_json_schema():
    """Editors validate against the JSON schemas, so the shipped data must pass them too."""
    for name, schema in json_schemas().items():
        directory = (DATA_DIR / name).parent
        stem = "*" if name.startswith("events/") else name.removesuffix(".schema.json")
        for path in directory.glob(f"{stem}.yaml"):
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            errors = [e.message for e in Draft202012Validator(schema).iter_errors(data)]
            assert not errors, f"{path.name}: {errors}"


def test_misspelled_field_names_file_field_and_problem(data_dir: Path):
    edit(data_dir / "units.yaml", "strength: 4", "strenght: 4")

    message = rejected(data_dir)

    assert "units.yaml" in message
    assert "units[swordsman].strenght: Extra inputs are not permitted" in message
    assert "units[swordsman].strength: Field required" in message


def test_negative_cost_is_rejected(data_dir: Path):
    edit(data_dir / "buildings.yaml", "cost: {wood: 4}", "cost: {wood: -4}")

    message = rejected(data_dir)

    assert "buildings.yaml" in message
    assert "buildings[farm].cost.wood: Input should be greater than or equal to 0" in message


def test_unknown_resource_is_rejected(data_dir: Path):
    edit(data_dir / "terrain.yaml", "yields: {food: 2}", "yields: {stone: 2}")

    assert "terrains[plains].yields.stone" in rejected(data_dir)


@pytest.mark.parametrize(
    ("file", "old", "new", "expected"),
    [
        (
            "units.yaml",
            "trained_in: barracks",
            "trained_in: barrack",
            "units.yaml: swordsman.trained_in: unknown building 'barrack'",
        ),
        (
            "units.yaml",
            "target: horseman",
            "target: knight",
            "units.yaml: spearman.counters: unknown unit 'knight'",
        ),
        (
            "buildings.yaml",
            "[hills, iron_deposit]",
            "[hill, iron_deposit]",
            "buildings.yaml: mine: unknown terrain 'hill'",
        ),
        (
            "events/barbarians.yaml",
            "unit: swordsman",
            "unit: berserker",
            "events/barbarians.yaml: spawn_neutral_army: unknown unit 'berserker'",
        ),
        (
            "balance.yaml",
            "unit: settler",
            "unit: colonist",
            "balance.yaml: start.units: unknown unit 'colonist'",
        ),
    ],
)
def test_broken_reference_is_named(data_dir: Path, file: str, old: str, new: str, expected: str):
    edit(data_dir / file, old, new)

    message = rejected(data_dir)

    assert "broken references" in message
    assert expected in message


def test_duplicate_id_is_rejected(data_dir: Path):
    edit(data_dir / "units.yaml", "id: swordsman", "id: spearman")

    assert "units.yaml: units: duplicate id 'spearman'" in rejected(data_dir)


def test_event_id_must_match_its_file_name(data_dir: Path):
    edit(data_dir / "events" / "plague.yaml", "id: plague", "id: pestilence")

    assert "id 'pestilence' must match the file name 'plague'" in rejected(data_dir)


def test_event_probability_above_one_is_rejected(data_dir: Path):
    edit(data_dir / "events" / "plague.yaml", "0.04", "4")

    assert "probability_per_round: Input should be less than or equal to 1" in rejected(data_dir)


def test_event_without_effect_is_rejected(data_dir: Path):
    edit(data_dir / "events" / "plague.yaml", "population_change: -1", "population_change: 0")

    assert "effects must set at least one effect" in rejected(data_dir)


def test_inverted_range_is_rejected(data_dir: Path):
    edit(data_dir / "balance.yaml", "{min: 0.8, max: 1.2}", "{min: 1.2, max: 0.8}")

    assert "combat.random_factor: Value error, min must not exceed max" in rejected(data_dir)


def test_resolution_order_must_list_each_step_once(data_dir: Path):
    edit(data_dir / "balance.yaml", "combat, production", "production")

    assert "resolution_order must list each step once" in rejected(data_dir)


def test_every_city_focus_needs_its_resource(data_dir: Path):
    edit(data_dir / "balance.yaml", "    military: iron\n", "")

    message = rejected(data_dir)

    assert "balance.yaml" in message
    assert "focus_yields must name every city focus, missing: military" in message


def test_invalid_yaml_is_reported_with_its_file(data_dir: Path):
    edit(data_dir / "victory.yaml", "rounds: 60", "rounds: [60")

    message = rejected(data_dir)

    assert "victory.yaml: not valid YAML" in message


def test_missing_file_is_reported(data_dir: Path):
    (data_dir / "treaties.yaml").unlink()

    assert "treaties.yaml: file is missing" in rejected(data_dir)


def test_missing_events_are_reported(data_dir: Path):
    for path in (data_dir / "events").glob("*.yaml"):
        path.unlink()

    assert "no event files found" in rejected(data_dir)


def test_rules_summary_mentions_every_unit_building_and_treaty():
    data = load_civ_data()
    rules = (DATA_DIR.parent / "rules.md").read_text(encoding="utf-8")

    for entry_id in [*data.units, *data.buildings, *data.treaties, *data.terrain]:
        assert entry_id in rules, f"rules.md does not mention '{entry_id}'"


def rules_table(first_header: str) -> dict[str, list[str]]:
    """Rows of the rules.md table whose header starts with ``first_header``, keyed by id."""
    lines = (DATA_DIR.parent / "rules.md").read_text(encoding="utf-8").splitlines()
    start = lines.index(next(line for line in lines if line.startswith(f"| {first_header} |")))
    rows: dict[str, list[str]] = {}
    for line in lines[start + 2 :]:
        if not line.startswith("|"):
            break
        first, *cells = [cell.strip() for cell in line.strip("|").split("|")]
        for entry_id in first.removesuffix(" (rare)").split(", "):
            rows[entry_id] = cells
    return rows


def amounts(text: str) -> dict[str, int]:
    """``"3 iron, 2 food"`` -> ``{"iron": 3, "food": 2}``; ``"—"`` -> ``{}``."""
    if text == "—":
        return {}
    return {name: int(count) for count, name in (part.split() for part in text.split(", "))}


def test_rules_unit_table_matches_the_data():
    units = load_civ_data().units
    rows = rules_table("Unit")

    assert set(rows) == set(units)
    for unit_id, (cost, strength, movement, upkeep, _notes) in rows.items():
        unit = units[unit_id]
        assert amounts(cost) == unit.cost, unit_id
        assert int(strength) == unit.strength, unit_id
        assert int(movement) == unit.movement, unit_id
        assert amounts(upkeep) == unit.upkeep, unit_id


def test_rules_building_table_matches_the_data():
    buildings = load_civ_data().buildings
    rows = rules_table("Building")

    assert set(rows) == set(buildings)
    for building_id, (cost, _effect) in rows.items():
        assert amounts(cost) == buildings[building_id].cost, building_id


def test_rules_terrain_table_matches_the_data():
    terrain = load_civ_data().terrain
    rows = rules_table("Terrain")

    assert set(rows) == set(terrain)
    for terrain_id, (yields, move, _defense) in rows.items():
        expected_move = None if move == "impassable" else int(move.split(",")[0])
        assert amounts(yields) == terrain[terrain_id].yields, terrain_id
        assert expected_move == terrain[terrain_id].movement_cost, terrain_id


@pytest.mark.parametrize("value", ["60.5", "60.0"])
def test_map_tiles_must_be_whole_numbers(data_dir: Path, value: str):
    edit(data_dir / "balance.yaml", "tiles: {min: 60,", f"tiles: {{min: {value},")

    assert "map.tiles.min: Input should be a valid integer" in rejected(data_dir)


@pytest.mark.parametrize(
    ("old", "new", "expected"),
    [
        ("    forest: 22", "    jungle: 22", "map.terrain_weights: unknown terrain 'jungle'"),
        (
            "    forest: 22",
            "    gold_vein: 22",
            "map.terrain_weights: 'gold_vein' is rare, set its number in map.rare_tiles",
        ),
        (
            "rare_tiles: {iron_deposit: 2, gold_vein: 2}",
            "rare_tiles: {iron_deposit: 2}",
            "map.rare_tiles must name exactly the rare terrains (gold_vein, iron_deposit), "
            "got iron_deposit",
        ),
        (
            "capital_terrain: plains",
            "capital_terrain: water",
            "map.capital_terrain: 'water' is impassable",
        ),
        (
            "    gold: [plains, plains, forest, forest, hills, hills]",
            "    gold: [plains, plains, forest, forest, hills]",
            "map.start_regions.gold: 5 tiles, but a capital works 6 (city.work_radius 1)",
        ),
        (
            "  work_radius: 1",
            "  work_radius: 2",
            "map.start_regions.food: 6 tiles, but a capital works 18 (city.work_radius 2)",
        ),
        (
            "    iron: [plains, plains, forest, forest, river, river]",
            "    iron: [plains, plains, forest, forest, river, mountains]",
            "map.start_regions.iron: 'mountains' is impassable",
        ),
        (
            "    wood: [plains, plains, hills, hills, river, river]",
            "    wood: [plains, plains, hills, hills, river, swamp]",
            "map.start_regions.wood: unknown terrain 'swamp'",
        ),
        (
            "    food: [forest, forest, hills, hills, river, river]\n",
            "",
            "map.start_regions.food: missing",
        ),
    ],
)
def test_map_numbers_the_generator_cannot_use_are_named(
    data_dir: Path, old: str, new: str, expected: str
):
    edit(data_dir / "balance.yaml", old, new)

    assert f"balance.yaml: {expected}" in rejected(data_dir)


@pytest.mark.parametrize(("old", "new"), [("width: 10", "width: 0"), ("plains: 34", "plains: 0")])
def test_map_width_and_terrain_weights_must_be_positive(data_dir: Path, old: str, new: str):
    edit(data_dir / "balance.yaml", old, new)

    assert "greater than or equal to 1" in rejected(data_dir)
