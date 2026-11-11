"""GET /setup: what the new-match form offers."""

import shutil

import pytest
import yaml
from fastapi.testclient import TestClient

from arena.api.app import app
from arena.api.setup import PERSONALITIES_DIR, load_personalities
from arena.config import load_config

client = TestClient(app)


def test_setup_lists_the_models_personalities_and_caps_of_the_config():
    options = client.get("/setup").json()

    config = load_config()
    assert options["model_seats"] is False
    assert options["models"] == [{"id": key, "model": m.model} for key, m in config.models.items()]
    assert options["caps"] == {
        "match_eur": float(config.limits.match_eur),
        "month_eur": float(config.limits.month_eur),
    }
    by_id = {p["id"]: p for p in options["personalities"]}
    assert set(by_id) == {p.stem for p in PERSONALITIES_DIR.glob("*.yaml")}
    knight = yaml.safe_load((PERSONALITIES_DIR / "honourable_knight.yaml").read_text("utf-8"))
    assert by_id["honourable_knight"] == {
        "id": "honourable_knight",
        "name": knight["name"],
        "description": knight["description"].strip(),
    }


@pytest.fixture
def personalities(tmp_path):
    shutil.copy(PERSONALITIES_DIR / "personality.schema.json", tmp_path)
    shutil.copy(PERSONALITIES_DIR / "opportunist.yaml", tmp_path)
    return tmp_path


def test_personality_that_breaks_the_schema_is_refused_with_its_file(personalities):
    (personalities / "loud.yaml").write_text("id: loud\nname: Loud\n", encoding="utf-8")

    with pytest.raises(ValueError, match=r"^loud\.yaml: "):
        load_personalities(personalities)


def test_personality_whose_id_is_not_its_file_name_is_refused(personalities):
    shutil.copy(personalities / "opportunist.yaml", personalities / "schemer.yaml")

    with pytest.raises(ValueError, match="schemer.yaml: id 'opportunist' must match"):
        load_personalities(personalities)
