import json
from pathlib import Path

import pytest
import yaml
from jsonschema import validate

ROOT = Path(__file__).resolve().parents[1]
ROLE_FILES = sorted((ROOT / "roles").glob("*.yaml"))
SCHEMA = json.loads((ROOT / "roles" / "role.schema.json").read_text(encoding="utf-8"))


def load(path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_expected_role_count():
    assert len(ROLE_FILES) == 16


@pytest.mark.parametrize("path", ROLE_FILES, ids=lambda p: p.stem)
def test_role_matches_schema(path):
    data = load(path)
    validate(data, SCHEMA)
    assert data["id"] == path.stem
    assert not isinstance(data["weight"], bool)


@pytest.mark.parametrize("path", ROLE_FILES, ids=lambda p: p.stem)
def test_rules_snippet_is_one_to_three_sentences(path):
    snippet = " ".join(load(path)["rules_snippet"].split())
    sentences = [s for s in snippet.replace("?", ".").replace("!", ".").split(".") if s.strip()]
    assert 1 <= len(sentences) <= 3, snippet


def test_ids_unique():
    ids = [load(p)["id"] for p in ROLE_FILES]
    assert len(ids) == len(set(ids))


def test_templates_are_fillable_and_valid():
    roles = {load(p)["id"]: load(p) for p in ROLE_FILES}
    templates = yaml.safe_load((ROOT / "templates.yaml").read_text(encoding="utf-8"))["templates"]
    assert len(templates) == 4
    for t in templates:
        counts = {r: n for r, n in t.get("roles", {}).items() if n != "fill"}
        assert set(counts) <= set(roles), t["id"]
        fixed = sum(counts.values())
        assert fixed <= t["min_players"], f"{t['id']}: {fixed} fixed roles > min_players"
        for role_id, n in counts.items():
            assert not (roles[role_id]["unique"] and n > 1), f"{t['id']}: {role_id} is unique"
        if "roles" in t:
            wolves = sum(n for r, n in counts.items() if roles[r]["team"] == "wolves")
            assert 1 <= wolves < t["min_players"] / 2, f"{t['id']}: wolves {wolves}"
