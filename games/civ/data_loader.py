"""Load and validate the Throne of Tokens content in ``games/civ/data/``.

This module only reads YAML and checks it. It holds no game rules: the numbers
mean something only to the systems that use them.

    data = load_civ_data()
    data.units["spearman"].strength  # 3

Bad data raises :class:`CivDataError` naming the file, the field and the problem.
The JSON schemas next to the data files are generated from the models here:

    uv run python -m games.civ.data_loader --write-schemas
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Annotated, Any, Literal, get_args

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

DATA_DIR = Path(__file__).parent / "data"

Id = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]*$", description="snake_case English id")]
Ratio = Annotated[float, Field(ge=0, le=1)]
Modifier = Annotated[float, Field(ge=-1, le=10, description="Relative change: 0.25 = +25 %")]
Resource = Literal["food", "wood", "iron", "gold"]
Focus = Literal["growth", "production", "military"]
Amounts = dict[Resource, Annotated[int, Field(ge=0)]]


class CivDataError(ValueError):
    """The content in the data directory is missing, malformed or inconsistent."""


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class _Named(_Model):
    id: Id
    name: str = Field(min_length=1, description="English display name")
    name_de: str = Field(min_length=1, description="German display name")


class UnitCount(_Model):
    unit: Id
    count: Annotated[int, Field(ge=1)]


# --- terrain.yaml -----------------------------------------------------------


class Terrain(_Named):
    yields: Amounts = Field(default_factory=dict, description="Per round, for the working city")
    movement_cost: Annotated[int, Field(ge=1)] | None = Field(
        description="Movement points to enter; null = impassable"
    )
    defense: Modifier = Field(0.0, description="Defender bonus on this tile")
    crossing_extra_cost: Annotated[int, Field(ge=0)] = Field(
        0, description="Extra movement points to cross (rivers)"
    )
    attacker_modifier: Modifier = Field(0.0, description="Applied to armies attacking this tile")
    rare: bool = False


class TerrainFile(_Model):
    terrains: list[Terrain] = Field(min_length=1)


# --- buildings.yaml ---------------------------------------------------------


class BuildingEffects(_Model):
    yields: Amounts = Field(default_factory=dict, description="Extra yield per round")
    trade_fee_modifier: Modifier = 0.0
    training_cost_modifier: Modifier = 0.0
    city_defense: Modifier = 0.0
    trained_unit_strength_bonus: Annotated[int, Field(ge=0)] = 0
    famine_delay_rounds: Annotated[int, Field(ge=0)] = 0
    vision_bonus: Annotated[int, Field(ge=0)] = 0


class Building(_Named):
    cost: Amounts = Field(min_length=1)
    effects: BuildingEffects
    requires_adjacent_terrain: list[Id] = Field(
        default_factory=list, description="City must border one of these terrains"
    )
    max_per_city: Annotated[int, Field(ge=1)] = 1


class BuildingRules(_Model):
    build_rounds: Annotated[int, Field(ge=1)]
    demolish_refund: Ratio


class BuildingsFile(_Model):
    rules: BuildingRules
    buildings: list[Building] = Field(min_length=1)


# --- units.yaml -------------------------------------------------------------


class Counter(_Model):
    target: Id = Field(description="Unit id this unit is strong against")
    multiplier: Annotated[float, Field(gt=1)]


class Unit(_Named):
    cost: Amounts = Field(min_length=1)
    strength: Annotated[int, Field(ge=0)]
    movement: Annotated[int, Field(ge=1)]
    upkeep: Amounts = Field(default_factory=dict, description="Per round")
    counters: list[Counter] = Field(default_factory=list)
    trained_in: Id | None = Field(description="Building id required to train; null = any city")
    ranged: bool = False
    first_strike: bool = False
    city_defense: Modifier = Field(0.0, description="Extra strength when defending a city")
    vs_walls_multiplier: Annotated[float, Field(ge=1)] = 1.0
    founds_city: bool = False
    vision_bonus: Annotated[int, Field(ge=0)] = 0
    auto_retreat: bool = False


class UnitsFile(_Model):
    units: list[Unit] = Field(min_length=1)


# --- events/*.yaml ----------------------------------------------------------


class EventEffects(_Model):
    population_change: int = 0
    yield_modifiers: dict[Resource, Modifier] = Field(default_factory=dict)
    resources: Amounts = Field(default_factory=dict, description="Granted once")
    city_becomes_neutral: bool = False
    spawn_neutral_army: list[UnitCount] = Field(default_factory=list)


class Event(_Named):
    probability_per_round: Ratio
    target: Literal["city", "region", "nation", "map"]
    region_radius: Annotated[int, Field(ge=1)] | None = None
    duration_rounds: Annotated[int, Field(ge=1)] = Field(
        1,
        description="Productions it holds, from the next round on (events strike after production)",
    )
    only_conquered_within_rounds: Annotated[int, Field(ge=1)] | None = None
    effects: EventEffects

    @model_validator(mode="after")
    def _check(self) -> Event:
        if self.effects == EventEffects():
            raise ValueError("effects must set at least one effect")
        if (self.target == "region") != (self.region_radius is not None):
            raise ValueError("region_radius is required for target 'region' and only for it")
        return self


# --- treaties.yaml ----------------------------------------------------------


class Duration(_Model):
    default: Annotated[int, Field(ge=1)]
    min: Annotated[int, Field(ge=1)]
    max: Annotated[int, Field(ge=1)]

    @model_validator(mode="after")
    def _check(self) -> Duration:
        if not self.min <= self.default <= self.max:
            raise ValueError("needs min <= default <= max")
        return self


class Treaty(_Named):
    duration_rounds: Duration | None = Field(description="null = until broken")
    forbids_attack: bool = False
    shared_vision: bool = False
    joint_war: bool = False
    open_borders: bool = False
    payment_per_round: bool = False


class Reputation(_Model):
    min: int
    max: int
    start: int
    break_treaty_penalty: Annotated[int, Field(le=0)]

    @model_validator(mode="after")
    def _check(self) -> Reputation:
        if not self.min <= self.start <= self.max:
            raise ValueError("needs min <= start <= max")
        return self


class TreatiesFile(_Model):
    reputation: Reputation
    treaties: list[Treaty] = Field(min_length=1)


# --- victory.yaml -----------------------------------------------------------


class Domination(_Model):
    city_share: Annotated[float, Field(gt=0, le=1)]


class Economy(_Model):
    gold: Annotated[int, Field(ge=1)]
    hold_rounds: Annotated[int, Field(ge=1)]
    public_countdown: bool


class Score(_Model):
    per_city: int
    per_population: int
    gold_divisor: Annotated[int, Field(ge=1)]
    reputation_divisor: Annotated[int, Field(ge=1)]


class RoundLimit(_Model):
    rounds: Annotated[int, Field(ge=1)]
    score: Score


class VictoryFile(_Model):
    domination: Domination
    economy: Economy
    round_limit: RoundLimit


# --- balance.yaml -----------------------------------------------------------


class Range(_Model):
    min: Annotated[float, Field(ge=0)]
    max: Annotated[float, Field(ge=0)]

    @model_validator(mode="after")
    def _check(self) -> Range:
        if self.min > self.max:
            raise ValueError("min must not exceed max")
        return self


class IntRange(_Model):
    min: Annotated[int, Field(ge=1, strict=True)]
    max: Annotated[int, Field(ge=1, strict=True)]

    @model_validator(mode="after")
    def _check(self) -> IntRange:
        if self.min > self.max:
            raise ValueError("min must not exceed max")
        return self


class MapBalance(_Model):
    tiles: IntRange = Field(description="Map size; grows with the number of nations")
    nations: IntRange
    width: Annotated[int, Field(ge=1)] = Field(description="Tiles per row")
    fog_vision_radius: Annotated[int, Field(ge=0)]
    terrain_weights: dict[Id, Annotated[int, Field(ge=1)]] = Field(
        min_length=1, description="Relative frequency of a terrain outside the start regions"
    )
    rare_tiles: dict[Id, Annotated[int, Field(ge=0)]] = Field(
        description="Tiles of each rare terrain per map"
    )
    capital_terrain: Id
    start_regions: dict[Resource, list[Id]] = Field(
        description="Terrain of the tiles a capital works, by the resource the nation is short of"
    )


class StartBalance(_Model):
    resources: Amounts
    units: list[UnitCount] = Field(min_length=1)


class BuildingSlots(_Model):
    base: Annotated[int, Field(ge=0)]
    population_divisor: Annotated[int, Field(ge=1)]
    max: Annotated[int, Field(ge=1)]


class CityBalance(_Model):
    base_yields: Amounts
    work_radius: Annotated[int, Field(ge=1)]
    expanded_work_radius: Annotated[int, Field(ge=1)]
    expanded_at_population: Annotated[int, Field(ge=1)]
    min_distance: Annotated[int, Field(ge=1)] = Field(
        description="A new city must be at least this many steps from every other city"
    )
    growth_food: Annotated[int, Field(ge=1)]
    food_per_population: Annotated[int, Field(ge=0)]
    building_slots: BuildingSlots
    focus_yields: dict[Focus, Resource] = Field(
        description="Which resource each population adds under a city focus"
    )

    @model_validator(mode="after")
    def _check(self) -> CityBalance:
        if missing := [focus for focus in get_args(Focus) if focus not in self.focus_yields]:
            raise ValueError(
                f"focus_yields must name every city focus, missing: {', '.join(missing)}"
            )
        return self


class ArmyBalance(_Model):
    max_units: Annotated[int, Field(ge=1)]
    fortify_defense: Modifier
    starving_units_lost_per_round: Annotated[int, Field(ge=0)]


class CombatBalance(_Model):
    random_factor: Range
    ranged_rounds: Annotated[int, Field(ge=0)]
    winner_loss_factor: Ratio


class ConquestBalance(_Model):
    population_loss: Annotated[int, Field(ge=0)]
    capital_lost_production_modifier: Modifier
    capital_lost_rounds: Annotated[int, Field(ge=1)]
    pillage_loot_share: Ratio


class WarWeariness(_Model):
    production_modifier_per_round: Modifier
    max_production_modifier: Modifier


class TradeBalance(_Model):
    base_fee: Ratio
    low_reputation_below: int
    low_reputation_extra_fee: Ratio
    max_rounds: Annotated[int, Field(ge=1)] = Field(description="The longest trade one can agree")


Step = Literal["trade", "build_and_train", "movement", "combat", "production", "growth", "events"]


class TurnBalance(_Model):
    info_tool_calls: Annotated[int, Field(ge=0)]
    diplomacy_passes: Annotated[int, Field(ge=1)]
    resolution_order: list[Step]

    @model_validator(mode="after")
    def _check(self) -> TurnBalance:
        if sorted(self.resolution_order) != sorted(Step.__args__):
            raise ValueError(f"resolution_order must list each step once: {list(Step.__args__)}")
        return self


class BalanceFile(_Model):
    map: MapBalance
    start: StartBalance
    city: CityBalance
    army: ArmyBalance
    combat: CombatBalance
    conquest: ConquestBalance
    war_weariness: WarWeariness
    trade: TradeBalance
    turn: TurnBalance


# --- loading ----------------------------------------------------------------

FILES: dict[str, type[_Model]] = {
    "terrain.yaml": TerrainFile,
    "buildings.yaml": BuildingsFile,
    "units.yaml": UnitsFile,
    "treaties.yaml": TreatiesFile,
    "victory.yaml": VictoryFile,
    "balance.yaml": BalanceFile,
}
EVENTS_DIR = "events"
EVENT_SCHEMA = "events/event.schema.json"


class CivData(_Model):
    """All content, with every list turned into a mapping by id."""

    terrain: dict[str, Terrain]
    buildings: dict[str, Building]
    building_rules: BuildingRules
    units: dict[str, Unit]
    events: dict[str, Event]
    treaties: dict[str, Treaty]
    reputation: Reputation
    victory: VictoryFile
    balance: BalanceFile


def load_civ_data(data_dir: Path = DATA_DIR) -> CivData:
    """Read every data file, validate it and check that cross-references resolve."""
    files = {name: _load_file(data_dir / name, model) for name, model in FILES.items()}
    events_dir = data_dir / EVENTS_DIR
    event_paths = sorted(events_dir.glob("*.yaml"))
    if not event_paths:
        raise CivDataError(f"{events_dir}: no event files found")
    events = [_load_file(path, Event) for path in event_paths]
    for path, event in zip(event_paths, events, strict=True):
        if path.stem != event.id:
            raise CivDataError(f"{path}: id '{event.id}' must match the file name '{path.stem}'")

    terrain: TerrainFile = files["terrain.yaml"]
    buildings: BuildingsFile = files["buildings.yaml"]
    units: UnitsFile = files["units.yaml"]
    treaties: TreatiesFile = files["treaties.yaml"]
    data = CivData(
        terrain=_by_id(data_dir / "terrain.yaml", "terrains", terrain.terrains),
        buildings=_by_id(data_dir / "buildings.yaml", "buildings", buildings.buildings),
        building_rules=buildings.rules,
        units=_by_id(data_dir / "units.yaml", "units", units.units),
        events={event.id: event for event in events},
        treaties=_by_id(data_dir / "treaties.yaml", "treaties", treaties.treaties),
        reputation=treaties.reputation,
        victory=files["victory.yaml"],
        balance=files["balance.yaml"],
    )
    _check_references(data_dir, data)
    return data


def _load_file[M: _Model](path: Path, model: type[M]) -> M:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise CivDataError(f"{path}: file is missing") from None
    except yaml.YAMLError as exc:
        raise CivDataError(f"{path}: not valid YAML: {exc}") from None
    try:
        return model.model_validate(raw)
    except ValidationError as exc:
        raise CivDataError(f"{path}: {_describe(exc, raw)}") from None


def _describe(exc: ValidationError, raw: Any) -> str:
    problems = []
    for error in exc.errors():
        problems.append(f"  {_where(error['loc'], raw)}: {error['msg']}")
    count = len(problems)
    return f"{count} problem{'s' if count > 1 else ''}\n" + "\n".join(problems)


def _where(loc: tuple[int | str, ...], raw: Any) -> str:
    """Render an error location, naming list entries by their id: ``units[swordsman].cost``."""
    text, node = "", raw
    for part in loc:
        if isinstance(part, int):
            node = node[part] if isinstance(node, list) and part < len(node) else None
            label = node.get("id") if isinstance(node, dict) else None
            text += f"[{label if isinstance(label, str) else part}]"
        else:
            node = node.get(part) if isinstance(node, dict) else None
            text += f".{part}" if text else part
    return text or "(top level)"


def _by_id[T: _Named](path: Path, key: str, items: list[T]) -> dict[str, T]:
    result: dict[str, T] = {}
    for item in items:
        if item.id in result:
            raise CivDataError(f"{path}: {key}: duplicate id '{item.id}'")
        result[item.id] = item
    return result


def _check_references(data_dir: Path, data: CivData) -> None:
    problems: list[str] = []

    def need(kind: str, known: dict[str, Any], ref: str, where: str) -> None:
        if ref not in known:
            problems.append(f"{where}: unknown {kind} '{ref}' (known: {', '.join(known)})")

    for building in data.buildings.values():
        for ref in building.requires_adjacent_terrain:
            need("terrain", data.terrain, ref, f"buildings.yaml: {building.id}")
    for unit in data.units.values():
        if unit.trained_in is not None:
            need("building", data.buildings, unit.trained_in, f"units.yaml: {unit.id}.trained_in")
        for counter in unit.counters:
            need("unit", data.units, counter.target, f"units.yaml: {unit.id}.counters")
    for event in data.events.values():
        for group in event.effects.spawn_neutral_army:
            need("unit", data.units, group.unit, f"events/{event.id}.yaml: spawn_neutral_army")
    for group in data.balance.start.units:
        need("unit", data.units, group.unit, "balance.yaml: start.units")
    problems += _map_problems(data)

    if problems:
        raise CivDataError(f"{data_dir}: broken references\n  " + "\n  ".join(problems))


def _map_problems(data: CivData) -> list[str]:
    """What the map generator could not work with."""
    problems: list[str] = []
    balance, terrain = data.balance.map, data.terrain
    rare = {terrain_id for terrain_id, entry in terrain.items() if entry.rare}

    def known(ref: str, where: str) -> bool:
        if ref not in terrain:
            problems.append(f"{where}: unknown terrain '{ref}' (known: {', '.join(terrain)})")
        return ref in terrain

    def passable(ref: str, where: str) -> None:
        if known(ref, where) and terrain[ref].movement_cost is None:
            problems.append(f"{where}: '{ref}' is impassable")

    for ref in balance.terrain_weights:
        if known(ref, "balance.yaml: map.terrain_weights") and ref in rare:
            problems.append(
                f"balance.yaml: map.terrain_weights: '{ref}' is rare, set its number in "
                "map.rare_tiles"
            )
    if set(balance.rare_tiles) != rare:
        problems.append(
            f"balance.yaml: map.rare_tiles must name exactly the rare terrains "
            f"({', '.join(sorted(rare))}), got {', '.join(sorted(balance.rare_tiles))}"
        )
    passable(balance.capital_terrain, "balance.yaml: map.capital_terrain")
    radius = data.balance.city.work_radius
    ring = 3 * radius * (radius + 1)
    for resource in get_args(Resource):
        region = balance.start_regions.get(resource)
        where = f"balance.yaml: map.start_regions.{resource}"
        if region is None:
            problems.append(f"{where}: missing")
            continue
        if len(region) != ring:
            problems.append(
                f"{where}: {len(region)} tiles, but a capital works {ring} "
                f"(city.work_radius {radius})"
            )
        for ref in region:
            passable(ref, where)
    return problems


def json_schemas() -> dict[str, dict[str, Any]]:
    """The JSON schema for each data file, keyed by its path relative to the data directory."""
    schemas = {
        name.replace(".yaml", ".schema.json"): model.model_json_schema()
        for name, model in FILES.items()
    }
    schemas[EVENT_SCHEMA] = Event.model_json_schema()
    return schemas


def write_schemas(data_dir: Path = DATA_DIR) -> None:
    for name, schema in json_schemas().items():
        text = json.dumps(schema, indent=2, ensure_ascii=False) + "\n"
        (data_dir / name).write_text(text, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    if sys.argv[1:] == ["--write-schemas"]:
        write_schemas()
    else:
        load_civ_data()
        print(f"{DATA_DIR}: ok")
