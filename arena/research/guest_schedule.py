"""Generate a proposed explicit guest schedule. No model or API client is used."""

import argparse
import csv
import random
import sys
from pathlib import Path

import yaml


def rows(plan):
    rng = random.Random(plan["ordering_seed"])
    result = []
    for cell in plan["role_cells"]:
        guests = [guest["id"] for guest in plan["guests"]]
        rng.shuffle(guests)
        for guest in guests:
            seats = list(plan["hosts_in_fixed_relative_order"])
            seats.insert(int(cell["guest_seat"][1:]) - 1, guest)
            result.append(
                {
                    "order": len(result) + 1,
                    "guest": guest,
                    "guest_seat": cell["guest_seat"],
                    "expected_role": cell["role"],
                    "seed": plan["seed"],
                    **{f"p{i}": m for i, m in enumerate(seats, 1)},
                }
            )
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    args = parser.parse_args()
    plan = yaml.safe_load(args.plan.read_text(encoding="utf-8"))
    schedule = rows(plan)
    writer = csv.DictWriter(sys.stdout, fieldnames=list(schedule[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(schedule)


if __name__ == "__main__":
    main()
