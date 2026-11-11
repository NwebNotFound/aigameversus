"""Tag matches that were played before matches had a batch, from the log a batch runner keeps.

The runner writes one JSON line per match it started, ``{"order": 113, "match_id": "..."}``;
an order that appears twice is a match played again after a failure, and both are tagged.
A match's place in the batch is its order counted from the batch's first order. With the
experiment's schedule, every match's seed is checked against its row first, so a log of
another database or another plan tags nothing by mistake.

    arena batches backfill E1-A2_started.jsonl --id E1-A2 --label "..." --first-order 113 --of 120
"""

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path
from uuid import UUID

from arena.db.match_store import Batch, MatchStore


@dataclass
class Backfill:
    tagged: list[UUID] = field(default_factory=list)
    already: list[UUID] = field(default_factory=list)  # had this batch: nothing to do
    problems: list[str] = field(default_factory=list)  # left untouched, with the reason


def read_started(path: Path) -> list[tuple[int, UUID]]:
    """The (order, match id) of every line; ValueError naming the line for a bad one."""
    started = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
            started.append((int(entry["order"]), UUID(entry["match_id"])))
        except (ValueError, KeyError, TypeError) as error:
            raise ValueError(f"{path}:{number}: not an order and a match id ({error})") from None
    return started


def read_seeds(path: Path) -> dict[int, int]:
    """Order -> seed from an experiment's schedule CSV (columns `order` and `seed`)."""
    with path.open(encoding="utf-8", newline="") as file:
        return {int(row["order"]): int(row["seed"]) for row in csv.DictReader(file)}


async def backfill(
    store: MatchStore,
    started: list[tuple[int, UUID]],
    *,
    batch_id: str,
    label: str,
    first_order: int,
    of: int,
    seeds: dict[int, int] | None = None,
) -> Backfill:
    """Tag each started match with its batch. Running it again changes nothing."""
    done = Backfill()
    for order, match_id in started:
        index = order - first_order + 1
        if not 1 <= index <= of:
            done.problems.append(f"{match_id}: order {order} is outside the batch")
            continue
        if seeds is not None:
            record = await store.get(match_id)
            if record is not None and record.seed != seeds.get(order):
                done.problems.append(
                    f"{match_id}: seed {record.seed}, but order {order} of the schedule has "
                    f"{seeds.get(order)}"
                )
                continue
        batch = Batch(id=batch_id, label=label, index=index, of=of)
        try:
            outcome = await store.tag_batch(match_id, batch)
        except KeyError:
            done.problems.append(f"{match_id}: no such match in this database")
            continue
        if outcome == "tagged":
            done.tagged.append(match_id)
        elif outcome == "same":
            done.already.append(match_id)
        else:
            done.problems.append(f"{match_id}: already in another batch, left as it is")
    return done
