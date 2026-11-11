"""An experiment plan (`experiments/*.yaml`) and the list of matches it fixes.

    uv run python -m arena.research.experiment experiments/E1_liars_deck.yaml > schedule.csv

The plan is written before the first paid match and then left alone. Loading it
checks its shape and that its budgets fit under the monthly cap; `schedule`
turns its stages into every match to play: seed, seating, order. Nothing here
plays a match.
"""

import csv
import random
import sys
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from arena.research.design import blocks_of_four, guest_seatings, mirror_seatings, rotations

Effort = Literal["minimal", "low", "medium", "high"]


class PlanError(ValueError):
    """The plan is broken; the message says which field."""


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class PlanModel(_Strict):
    """A model as the plan saw it at the provider on the day it was written."""

    openrouter: str = Field(min_length=1)
    input_usd_per_mtok: Decimal = Field(ge=0)
    output_usd_per_mtok: Decimal = Field(ge=0)
    tier: Literal["cheap", "strong"]


class _Stage(_Strict):
    id: str = Field(min_length=1)
    title: str
    budget_eur: Decimal = Field(gt=0)  # the stage stops when its matches have cost this much
    estimate_eur: Decimal = Field(gt=0)
    seed_base: int = Field(ge=0)
    seeds: int = Field(gt=0)  # per table (league) or per model (mirror, guests)
    turn_timeout_s: int = Field(gt=0)
    max_output_tokens: int = Field(gt=0)
    notes: str = ""


class League(_Stage):
    """Eight models, every balanced table of four, each seed with four seatings."""

    kind: Literal["league"]
    models: list[str] = Field(min_length=8, max_length=8)
    effort: Effort
    pilot_tables: int = Field(ge=0)  # these tables' first seed is played before the rest
    pilot_budget_eur: Decimal = Field(gt=0)  # for the pilot matches; part of `budget_eur`


class Mirror(_Stage):
    """One model in all four seats, two of them at each of two reasoning efforts."""

    kind: Literal["mirror"]
    models: list[str] = Field(min_length=1)
    efforts: tuple[Effort, Effort]
    substitutes: list[str] = []


class Guests(_Stage):
    """One guest model at a table with three fixed host models."""

    kind: Literal["guests"]
    guests: list[str] = Field(min_length=1)
    hosts: list[str] = Field(min_length=3, max_length=3)
    effort: Effort
    substitutes: list[str] = []


Stage = Annotated[League | Mirror | Guests, Field(discriminator="kind")]


class Budget(_Strict):
    month_cap_eur: Decimal = Field(gt=0)
    spent_before_eur: Decimal = Field(ge=0)
    reserve_eur: Decimal = Field(ge=0)
    other_plans_eur: dict[str, Decimal] = {}  # money set aside for plans that are not this file


class Experiment(_Strict):
    id: str = Field(min_length=1)
    title: str
    version: int = Field(ge=1)
    status: Literal["proposed", "approved", "running", "closed"]
    registered: str
    author: str
    amendments: list[dict[str, Any]]
    approvals: list[dict[str, Any]]
    question: str
    game: str
    settings: dict[str, Any]
    conditions: dict[str, Any]
    models: dict[str, PlanModel]
    not_chosen: dict[str, Any]
    stages: list[Stage]
    hypotheses: list[dict[str, Any]]
    metrics: dict[str, Any]
    analysis: dict[str, Any]
    rules: dict[str, Any]
    budget: Budget
    limitations: list[str]

    @model_validator(mode="after")
    def _consistent(self) -> "Experiment":
        ids = [stage.id for stage in self.stages]
        if len(set(ids)) != len(ids):
            raise ValueError("two stages share an id")
        for stage in self.stages:
            unknown = sorted(set(_stage_models(stage)) - set(self.models))
            if unknown:
                raise ValueError(f"stage {stage.id} names models the plan does not list: {unknown}")
            if isinstance(stage, League) and stage.pilot_budget_eur > stage.budget_eur:
                raise ValueError(f"stage {stage.id}: the pilot budget is above the stage budget")
        budget = self.budget
        planned = (
            sum(stage.budget_eur for stage in self.stages)
            + sum(budget.other_plans_eur.values())
            + budget.spent_before_eur
            + budget.reserve_eur
        )
        if planned > budget.month_cap_eur:
            raise ValueError(
                f"budgets add up to {planned} EUR, above the monthly cap of "
                f"{budget.month_cap_eur} EUR"
            )
        return self


@dataclass(frozen=True)
class ScheduledMatch:
    order: int  # play in this order, starting at 1
    stage: str
    table: str  # which group of players, e.g. "T03" or a model id
    seating: int  # which seating of that table, starting at 1
    replicate: int  # which seed of that table, starting at 1
    seed: int
    pilot: bool
    seats: tuple[str, ...]  # `model@effort` for p1, p2, ...


def load_experiment(path: Path) -> Experiment:
    """Read and check a plan; raise PlanError with a readable message."""
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise PlanError(f"{path.name}: cannot read file: {error}") from error
    try:
        return Experiment.model_validate(data)
    except ValidationError as invalid:
        problems = "; ".join(
            f"{'.'.join(str(part) for part in problem['loc']) or 'file'}: {problem['msg']}"
            for problem in invalid.errors()
        )
        raise PlanError(f"{path.name}: {problems}") from invalid


def schedule(experiment: Experiment) -> list[ScheduledMatch]:
    """Every match of the plan, in the order to play it.

    Stages follow each other as in the file. Inside a stage the pilot matches
    come first, then one replicate after the other, so a stage that stops at
    its budget stops with whole replicates behind it. Inside a replicate the
    order is shuffled, with the stage's `seed_base` as the seed, so that no
    table is played at one time of day only.
    """
    matches: list[ScheduledMatch] = []
    for stage in experiment.stages:
        rows = _stage_rows(stage)
        groups: dict[tuple[bool, int], list[tuple]] = {}
        for row in rows:
            groups.setdefault((not row[4], row[2]), []).append(row)
        for key in sorted(groups):
            group = groups[key]
            random.Random(stage.seed_base + 1000 * key[1] + key[0]).shuffle(group)
            for table, seating, replicate, seed, pilot, seats in group:
                matches.append(
                    ScheduledMatch(
                        len(matches) + 1, stage.id, table, seating, replicate, seed, pilot, seats
                    )
                )
    return matches


def _stage_models(stage: League | Mirror | Guests) -> list[str]:
    if isinstance(stage, League):
        return stage.models
    if isinstance(stage, Mirror):
        return [*stage.models, *stage.substitutes]
    return [*stage.guests, *stage.hosts, *stage.substitutes]


def _stage_rows(stage: League | Mirror | Guests) -> list[tuple]:
    """(table, seating, replicate, seed, pilot, seats) for every match of a stage."""
    rows = []
    replicates = range(1, stage.seeds + 1)
    if isinstance(stage, League):
        for number, block in enumerate(blocks_of_four(stage.models), start=1):
            for replicate in replicates:
                seed = stage.seed_base + 10 * number + replicate
                pilot = number <= stage.pilot_tables and replicate == 1
                for seating, seats in enumerate(rotations(block), start=1):
                    entries = tuple(f"{model}@{stage.effort}" for model in seats)
                    rows.append((f"T{number:02d}", seating, replicate, seed, pilot, entries))
    elif isinstance(stage, Mirror):
        first, second = stage.efforts
        for model in stage.models:
            seatings = mirror_seatings(f"{model}@{first}", f"{model}@{second}")
            for replicate in replicates:
                for seating, seats in enumerate(seatings, start=1):
                    rows.append(
                        (model, seating, replicate, stage.seed_base + replicate, False, seats)
                    )
    else:
        hosts = [f"{host}@{stage.effort}" for host in stage.hosts]
        for guest in stage.guests:
            seatings = guest_seatings(f"{guest}@{stage.effort}", hosts)
            for replicate in replicates:
                for seating, seats in enumerate(seatings, start=1):
                    rows.append(
                        (guest, seating, replicate, stage.seed_base + replicate, False, seats)
                    )
    return rows


def write_csv(matches: list[ScheduledMatch], out: Any) -> None:
    """The schedule as CSV: one match per line, seats as `model@effort`."""
    seats = max(len(match.seats) for match in matches)
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(
        ["order", "stage", "table", "seating", "replicate", "seed", "pilot"]
        + [f"p{seat}" for seat in range(1, seats + 1)]
    )
    for match in matches:
        writer.writerow(
            [
                match.order,
                match.stage,
                match.table,
                match.seating,
                match.replicate,
                match.seed,
                int(match.pilot),
                *match.seats,
            ]
        )


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    if len(arguments) != 1:
        print("usage: python -m arena.research.experiment PLAN.yaml", file=sys.stderr)
        return 2
    try:
        experiment = load_experiment(Path(arguments[0]))
    except PlanError as error:
        print(error, file=sys.stderr)
        return 1
    write_csv(schedule(experiment), sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
