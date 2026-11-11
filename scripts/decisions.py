#!/usr/bin/env python3
"""One file per decision: docs/decisions/D-0NN-slug.md, listed in docs/DECISIONS.md.

    python scripts/decisions.py new D-107 "Title of the decision"   # a new entry to fill in
    python scripts/decisions.py index                               # rewrite the index, sorted
    python scripts/decisions.py adopt                               # old-style `## D-0NN · Title`
                                                                    # blocks in DECISIONS.md
                                                                    # become files
    python scripts/decisions.py adopt --from-ref HEAD               # a branch's own old-style
                                                                    # blocks, after merging main

Why: every author used to append to the end of one file, so every pull request that added a
decision conflicted with the next. Now a decision is its own file (no two pull requests touch
the same file) and the index has one line per decision (`merge=union` in .gitattributes keeps
both lines when two pull requests add one). `tests/test_decisions.py` checks that the files and
the index agree.

A pull request that still appends a block to the old file: `git merge origin/main`, then
`git checkout --theirs docs/DECISIONS.md` (the new index), then
`python scripts/decisions.py adopt --from-ref HEAD` (your own blocks become files), commit.
"""

import re
import subprocess
import sys
import unicodedata
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
DIR = DOCS / "decisions"
INDEX = DOCS / "DECISIONS.md"
LEGACY = re.compile(r"(?m)^## (D-\d{3}) · (.+)$")
NL = "\n"

HEADER = """# Decisions

Decisions taken where [DESIGN.md](DESIGN.md) is open, or where this project
deliberately differs from it. `DESIGN.md` is kept as the original spec, apart
from the author line and the game title (D-018); where the two disagree, the
decision wins.

Each decision is its own file in [decisions/](decisions/): date, decision, why,
alternatives considered. Numbers are `D-001` and up, never reused.

**To add one:** claim the next free number in the team's number list, then
`python scripts/decisions.py new D-0NN "Title"`, fill in the file, and keep the
line it added to the list below. Do not write decisions into this file: a
leftover `## D-0NN · Title` block here fails `tests/test_decisions.py`; move it
with `python scripts/decisions.py adopt`.

"""
TEMPLATE = """# {number} · {title}

- **Date:** {date}
- **Decision:**
- **Why:**
- **Alternatives:**
"""


def slug(title: str) -> str:
    plain = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()
    words = re.sub(r"[^a-z0-9]+", " ", plain.lower()).split()
    out = ""
    for word in words:
        if len(out) + len(word) + 1 > 60:
            break
        out = f"{out}-{word}" if out else word
    return out or "decision"


def entries() -> dict[str, tuple[str, str]]:
    """Number -> (title, file name) of every decision file."""
    found = {}
    for path in sorted(DIR.glob("D-*.md")):
        first = path.read_text(encoding="utf-8").splitlines()[0]
        match = re.match(r"^# (D-\d{3}) · (.+)$", first)
        if match:
            found[match.group(1)] = (match.group(2), path.name)
    return found


def write_index() -> None:
    lines = [
        f"- [{number}](decisions/{name}) · {title}"
        for number, (title, name) in sorted(entries().items())
    ]
    INDEX.write_text(HEADER + NL.join(lines) + NL, encoding="utf-8", newline=NL)


def blocks(text: str) -> list[tuple[str, str, str]]:
    """The old-style `## D-0NN · Title` blocks of a text: (number, title, body)."""
    marks = list(LEGACY.finditer(text))
    found = []
    for i, mark in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        body = text[mark.end() : end]
        # A conflict marker ends the entry; what follows belongs to the other side.
        body = re.split(r"(?m)^(<<<<<<<|=======|>>>>>>>) ", body)[0]
        found.append((mark.group(1), mark.group(2), body.strip(NL)))
    return found


def write_entry(number: str, title: str, body: str) -> None:
    DIR.mkdir(exist_ok=True)
    path = DIR / f"{number}-{slug(title)}.md"
    path.write_text(f"# {number} · {title}\n\n{body}\n", encoding="utf-8", newline=NL)


def adopt() -> list[str]:
    """Move every `## D-0NN · Title` block of DECISIONS.md into its own file."""
    text = INDEX.read_text(encoding="utf-8")
    found = blocks(text)
    if not found:
        return []
    for number, title, body in found:
        write_entry(number, title, body)
    head = text[: LEGACY.search(text).start()]
    INDEX.write_text(head.rstrip(NL) + NL, encoding="utf-8", newline=NL)
    write_index()
    return [number for number, _, _ in found]


def adopt_from(ref: str) -> list[str]:
    """Take the decisions a branch wrote into the old file, from its version at `ref`.

    Only blocks whose number has no file yet are written, so it is safe to run twice.
    """
    text = subprocess.run(
        ["git", "show", f"{ref}:docs/DECISIONS.md"],
        cwd=ROOT,
        capture_output=True,
        check=True,
        encoding="utf-8",
    ).stdout
    have = set(entries())
    moved = []
    for number, title, body in blocks(text):
        if number not in have:
            write_entry(number, title, body)
            moved.append(number)
    write_index()
    return moved


def new(number: str, title: str) -> Path:
    if not re.fullmatch(r"D-\d{3}", number):
        sys.exit(f"{number!r} is not a decision number like D-107")
    if number in entries():
        sys.exit(f"{number} already exists: take the next free number")
    DIR.mkdir(exist_ok=True)
    path = DIR / f"{number}-{slug(title)}.md"
    text = TEMPLATE.format(number=number, title=title, date=date.today().isoformat())
    path.write_text(text, encoding="utf-8", newline=NL)
    write_index()
    return path


def main(argv: list[str]) -> int:
    if argv[:1] == ["new"] and len(argv) == 3:
        print(new(argv[1], argv[2]))
    elif argv == ["index"]:
        write_index()
    elif argv == ["adopt"] or (argv[:2] == ["adopt", "--from-ref"] and len(argv) == 3):
        moved = adopt_from(argv[2]) if len(argv) == 3 else adopt()
        print(f"Moved {len(moved)} decision(s) into docs/decisions/: {', '.join(moved) or '-'}")
    else:
        sys.exit(__doc__)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
