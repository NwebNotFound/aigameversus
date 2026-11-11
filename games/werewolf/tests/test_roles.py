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


def test_ids_unique():
    ids = [load(p)["id"] for p in ROLE_FILES]
    assert len(ids) == len(set(ids))


def test_templates_reference_known_roles():
    ids = {load(p)["id"] for p in ROLE_FILES}
    templates = yaml.safe_load((ROOT / "templates.yaml").read_text(encoding="utf-8"))["templates"]
    assert len(templates) == 4
    for t in templates:
        assert set(t.get("roles", {})) <= ids
