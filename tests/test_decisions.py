"""Decisions are one file each in docs/decisions/, listed in docs/DECISIONS.md.

Unique numbers, the same four fields in every file, and the index and the files agree.
A decision still written as a `## D-0NN · Title` block in the index is moved by
`python scripts/decisions.py adopt`.
"""

import re
import subprocess
from pathlib import Path

import pytest

from scripts import decisions

ROOT = Path(__file__).resolve().parents[1]
FILES = sorted((ROOT / "docs" / "decisions").glob("D-*.md"))
INDEX = (ROOT / "docs" / "DECISIONS.md").read_text(encoding="utf-8")
HEADING = re.compile(r"^# (D-\d{3}) · (.+)$")
LISTED = re.findall(r"(?m)^- \[(D-\d{3})\]\(decisions/([^)]+)\) · (.+)$", INDEX)


def numbers() -> list[str]:
    return [
        HEADING.match(path.read_text(encoding="utf-8").splitlines()[0]).group(1) for path in FILES
    ]


def test_every_file_is_named_after_the_number_and_title_in_its_heading():
    assert FILES
    for path in FILES:
        heading = HEADING.match(path.read_text(encoding="utf-8").splitlines()[0])
        assert heading, f"{path.name}: the first line must be '# D-0NN · Title'"
        assert path.name.startswith(f"{heading.group(1)}-"), path.name


def test_numbers_are_unique():
    found = numbers()
    assert len(set(found)) == len(found), "two files have the same D-number: renumber the later"


def test_every_decision_has_date_decision_why_and_alternatives():
    for path in FILES:
        text = path.read_text(encoding="utf-8")
        for field in ("**Date:**", "**Decision:**", "**Why:**", "**Alternatives:**"):
            assert field in text, f"{path.name}: {field} is missing"


def test_the_index_lists_every_file_once_with_its_title():
    expected = {(n, name, title) for n, (title, name) in decisions.entries().items()}
    assert len(LISTED) == len(set(LISTED)), "a decision is listed twice in docs/DECISIONS.md"
    assert set(LISTED) == expected, (
        "docs/DECISIONS.md and docs/decisions/ differ: run `python scripts/decisions.py index`"
    )


def test_the_index_holds_no_decision_text_of_its_own():
    assert not re.search(r"(?m)^## D-\d{3}", INDEX), (
        "a decision is written into docs/DECISIONS.md: move it with "
        "`python scripts/decisions.py adopt`"
    )
    assert not re.search(r"(?m)^(<<<<<<<|=======|>>>>>>>)", INDEX), "unresolved merge conflict"


def test_new_makes_a_file_and_a_line_and_refuses_a_taken_number(tmp_path, monkeypatch):
    monkeypatch.setattr(decisions, "DIR", tmp_path / "decisions")
    monkeypatch.setattr(decisions, "INDEX", tmp_path / "DECISIONS.md")

    path = decisions.new("D-901", "A test: with ümlauts & symbols!")

    assert path.name == "D-901-a-test-with-umlauts-symbols.md"
    assert (
        path.read_text(encoding="utf-8").splitlines()[0]
        == "# D-901 · A test: with ümlauts & symbols!"
    )
    assert "- [D-901](decisions/D-901-a-test-with-umlauts-symbols.md) · A test" in (
        tmp_path / "DECISIONS.md"
    ).read_text(encoding="utf-8")
    with pytest.raises(SystemExit, match="already exists"):
        decisions.new("D-901", "Same number again")


def test_adopt_moves_old_style_blocks_into_files_and_lists_them(tmp_path, monkeypatch):
    monkeypatch.setattr(decisions, "DIR", tmp_path / "decisions")
    index = tmp_path / "DECISIONS.md"
    monkeypatch.setattr(decisions, "INDEX", index)
    index.write_text(
        "# Decisions\n\nintro\n\n## D-902 · One\n\n- **Date:** x\n- **Why:** y\n\n"
        "## D-903 · Two\n\n- **Date:** z\n",
        encoding="utf-8",
    )

    moved = decisions.adopt()

    assert moved == ["D-902", "D-903"]
    assert (tmp_path / "decisions" / "D-902-one.md").read_text(encoding="utf-8") == (
        "# D-902 · One\n\n- **Date:** x\n- **Why:** y\n"
    )
    text = index.read_text(encoding="utf-8")
    assert "## D-90" not in text and "- [D-903](decisions/D-903-two.md) · Two" in text


def test_every_d_number_mentioned_in_the_repository_exists():
    known = {int(n[2:]) for n in numbers()}
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
        if name.startswith("tests/test_decisions.py"):
            continue
        for number in re.findall(r"\bD-(\d{3})\b", content):
            if int(number) not in known:
                missing.setdefault(name, set()).add(int(number))
    assert not missing, missing
