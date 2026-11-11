import json
from pathlib import Path

import pytest
import yaml
from jsonschema import ValidationError, validate

DIR = Path(__file__).resolve().parents[2] / "config" / "personalities"
FILES = sorted(DIR.glob("*.yaml"))
SCHEMA = json.loads((DIR / "personality.schema.json").read_text(encoding="utf-8"))


def load(path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_five_personalities_exist():
    assert {p.stem for p in FILES} == {
        "paranoid_emperor",
        "merchant_republic",
        "honourable_knight",
        "opportunist",
        "silent_observer",
    }


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.stem)
def test_personality_matches_schema(path):
    data = load(path)
    validate(data, SCHEMA)
    assert data["id"] == path.stem


@pytest.mark.parametrize(
    "change",
    [
        {"values": {"risk_taking": 101, "honesty": 5, "aggression": 5}},
        {"values": {"risk_taking": 50, "honesty": 5}},
        {"values": {"risk_taking": 50.5, "honesty": 5, "aggression": 5}},
        {"id": "Bad Id"},
        {"extra": 1},
    ],
)
def test_broken_personality_is_rejected(change):
    with pytest.raises(ValidationError):
        validate(load(FILES[0]) | change, SCHEMA)
