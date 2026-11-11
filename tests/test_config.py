from decimal import Decimal

import pytest
import yaml

from arena.config import CONFIG_PATH, ConfigError, load_config

VALID = {
    "limits": {
        "match_eur": 0.5,
        "month_eur": 5,
        "usd_to_eur": 1.0,
        "max_input_tokens": 50000,
        "max_output_tokens": 1500,
    },
    "models": {
        "some-model": {
            "provider": "openrouter",
            "model": "some-vendor/some-model",
            "input_usd_per_mtok": 0.0399,
            "output_usd_per_mtok": 0.5,
        }
    },
}


def load(tmp_path, data):
    path = tmp_path / "models.yaml"
    path.write_text(data if isinstance(data, str) else yaml.safe_dump(data), encoding="utf-8")
    return load_config(path)


def changed(section, **fields):
    """VALID with some fields of one limit or model entry replaced; None removes a field."""
    data = yaml.safe_load(yaml.safe_dump(VALID))
    entry = data["limits"] if section == "limits" else data["models"]["some-model"]
    for name, value in fields.items():
        if value is None:
            del entry[name]
        else:
            entry[name] = value
    return data


def test_shipped_config_has_the_project_caps_and_a_roster():
    config = load_config()

    assert CONFIG_PATH.name == "models.yaml"
    assert (config.limits.match_eur, config.limits.month_eur) == (Decimal("0.50"), Decimal("5"))
    # A dollar never counts for less than a euro's worth of cap by default.
    assert config.limits.usd_to_eur >= 1
    # Enough different models for a Poker table.
    assert len(config.models) >= 6
    assert len({model.model for model in config.models.values()}) == len(config.models)
    assert all(model.output_usd_per_mtok > 0 for model in config.models.values())


def test_prices_are_read_exactly_as_written(tmp_path):
    model = load(tmp_path, VALID).models["some-model"]

    assert model.input_usd_per_mtok == Decimal("0.0399")
    assert model.output_usd_per_mtok == Decimal("0.5")


@pytest.mark.parametrize(
    ("data", "problem"),
    [
        (changed("limits", match_eur=0), "limits.match_eur"),
        (changed("limits", month_eur=-5), "limits.month_eur"),
        (changed("limits", usd_to_eur=None), "limits.usd_to_eur"),
        (changed("limits", max_output_tokens=0), "limits.max_output_tokens"),
        (changed("limits", max_input_tokens=1.5), "limits.max_input_tokens"),
        (changed("limits", day_eur=1), "limits.day_eur"),
        (changed("models", input_usd_per_mtok=-0.1), "models.some-model.input_usd_per_mtok"),
        (changed("models", output_usd_per_mtok=None), "models.some-model.output_usd_per_mtok"),
        (changed("models", provider="some-shop"), "models.some-model.provider"),
        (changed("models", model=""), "models.some-model.model"),
        (changed("models", api_key="sk-123"), "models.some-model.api_key"),
        ({"models": VALID["models"]}, "limits"),
        ({"limits": VALID["limits"]}, "models"),
        ("models: [", "cannot read file"),
        ("just text", "file"),
    ],
)
def test_broken_config_is_refused_with_the_field_that_is_wrong(tmp_path, data, problem):
    with pytest.raises(ConfigError, match=rf"^models\.yaml: .*{problem}"):
        load(tmp_path, data)


def test_missing_file_is_a_config_error(tmp_path):
    with pytest.raises(ConfigError, match="cannot read file"):
        load_config(tmp_path / "nowhere.yaml")
