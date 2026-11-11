import json
from pathlib import Path

import pytest
import yaml
from jsonschema import validate

from games.liars_deck.variants import (
    SCHEMA_PATH,
    VARIANTS_DIR,
    VariantError,
    json_schema,
    load_variant,
    load_variants,
)

VARIANT_FILES = sorted(VARIANTS_DIR.glob("*.yaml"))


def test_expected_variants_exist():
    assert set(load_variants()) == {"base", "devil_card"}


@pytest.mark.parametrize("path", VARIANT_FILES, ids=lambda p: p.stem)
def test_variant_validates(path):
    variant = load_variant(path)
    assert variant.deck.total == 20
    assert (variant.hand_size, variant.play.min_cards, variant.play.max_cards) == (5, 1, 3)
    assert (variant.revolver.chambers, variant.revolver.live) == (6, 1)
    assert (variant.players.min, variant.players.max) == (2, 4)


@pytest.mark.parametrize("path", VARIANT_FILES, ids=lambda p: p.stem)
def test_variant_matches_json_schema_file(path):
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    validate(yaml.safe_load(path.read_text(encoding="utf-8")), schema)


def test_schema_file_is_current():
    assert json.loads(SCHEMA_PATH.read_text(encoding="utf-8")) == json_schema()


def test_devil_card_is_data():
    variants = load_variants()
    assert variants["base"].devil_card is None
    devil = variants["devil_card"].devil_card
    assert (devil.effect, devil.trigger, devil.count) == (
        "all_others_shoot",
        "revealed_on_liar_call",
        1,
    )
    assert devil.replaces_normal_shot is True


def broken(tmp_path: Path, **changes) -> Path:
    data = yaml.safe_load((VARIANTS_DIR / "base.yaml").read_text(encoding="utf-8"))
    data.update(changes)
    path = tmp_path / "broken.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


@pytest.mark.parametrize(
    ("changes", "fragment"),
    [
        ({"id": "broken", "deck": {"kings": 6, "queens": 6, "aces": 6}}, "deck.jokers"),
        ({"id": "broken", "hand_size": "five"}, "hand_size"),
        ({"id": "broken", "revolver": {"chambers": 6, "live": 7}}, "revolver.live"),
        ({"id": "broken", "play": {"min_cards": 1, "max_cards": 9}}, "play.max_cards"),
        ({"id": "broken", "hand_size": 6}, "too small"),
        ({"id": "broken", "surprise": True}, "surprise"),
        ({"id": "other"}, "must match the file name"),
        (
            {
                "id": "broken",
                "devil_card": {
                    "card": "joker",
                    "count": 3,
                    "trigger": "revealed_on_liar_call",
                    "effect": "all_others_shoot",
                    "replaces_normal_shot": True,
                },
            },
            "devil_card.count",
        ),
    ],
)
def test_broken_variant_is_rejected_readably(tmp_path, changes, fragment):
    with pytest.raises(VariantError) as err:
        load_variant(broken(tmp_path, **changes))
    assert err.value.args[0].startswith("broken.yaml: ")
    assert fragment in str(err.value)


def test_unreadable_yaml_is_rejected(tmp_path):
    path = tmp_path / "bad.yaml"
    path.write_text("id: [unclosed", encoding="utf-8")
    with pytest.raises(VariantError, match="bad.yaml: cannot read file"):
        load_variant(path)
