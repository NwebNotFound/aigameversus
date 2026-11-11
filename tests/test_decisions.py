"""docs/DECISIONS.md stays a clean list: unique, ascending numbers and the same four fields."""

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEXT = (ROOT / "docs" / "DECISIONS.md").read_text(encoding="utf-8")
HEADINGS = re.findall(r"^## D-(\d+) · (.+)$", TEXT, flags=re.MULTILINE)
NUMBERS = [int(number) for number, _ in HEADINGS]


def test_every_decision_heading_has_a_number_and_a_title():
    assert len(HEADINGS) == len(re.findall(r"^## ", TEXT, flags=re.MULTILINE)) > 0


def test_numbers_are_unique_and_ascending():
    assert sorted(set(NUMBERS)) == NUMBERS, "renumber the later of two equal D-numbers"


def test_every_decision_has_date_decision_why_and_alternatives():
    for block in re.split(r"(?m)^## ", TEXT)[1:]:
        title = block.splitlines()[0]
        for field in ("**Date:**", "**Decision:**", "**Why:**", "**Alternatives:**"):
            assert field in block, f"{title}: {field} is missing"


def test_every_d_number_mentioned_in_the_repository_exists():
    files = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.splitlines()
    missing: dict[str, set[int]] = {}
    for name in files:
        if name.endswith((".png", ".gif", ".lock", ".json")) or name == "docs/DESIGN.md":
            continue
        try:
            content = (ROOT / name).read_text(encoding="utf-8")
        except (UnicodeDecodeError, FileNotFoundError):
            continue
        for number in re.findall(r"\bD-(\d{3})\b", content):
            if int(number) not in NUMBERS:
                missing.setdefault(name, set()).add(int(number))
    assert not missing, missing
