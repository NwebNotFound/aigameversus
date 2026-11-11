"""GET /models/catalog and model seats for models outside config/models.yaml.

OpenRouter's list is the sample of tests/test_catalog.py; LiteLLM answers from
its own mock with every name lookup refused. Nothing costs money.
"""

import pytest
from fastapi.testclient import TestClient

from arena.api.app import app
from tests.db.test_model_seats_api import KEY, PLAY_3, calls, finish
from tests.test_catalog import serve
from tests.test_cli import arena


@pytest.fixture
def client(database_url, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("ARENA_ALLOW_MODEL_SEATS", "1")
    monkeypatch.setenv("OPENROUTER_API_KEY", KEY)
    with TestClient(app) as client:
        yield client


def test_the_catalog_lists_verified_models_first_then_openrouters_others(client, monkeypatch):
    serve(monkeypatch)

    out = client.get("/models/catalog").json()

    models = {m["id"]: m for m in out["models"]}
    assert models["glm-flash"]["verified"] is True
    assert out["models"][0]["verified"] is True
    plays = models["acme/plays"]
    assert plays["verified"] is False
    assert (plays["input_usd_per_mtok"], plays["output_usd_per_mtok"]) == (1.0, 2.0)
    assert models["acme/pricey"]["high_price"] is True
    assert "acme/no-tool-choice" not in models
    assert out["fresh"] is True and out["fetched_at"] is not None


def test_offline_without_a_copy_the_catalog_is_the_config(client):
    out = client.get("/models/catalog").json()

    assert all(m["verified"] for m in out["models"])
    assert (out["fetched_at"], out["fresh"]) == (None, False)


def test_a_catalog_model_takes_a_seat_at_openrouters_prices(
    client, database_url, monkeypatch, answer_with
):
    serve(monkeypatch)
    sent = answer_with(**PLAY_3)

    response = client.post(
        "/matches",
        json={"game": "toy", "models": ["acme/plays", "glm-flash"], "confirm_spend": True},
    )

    assert response.status_code == 201, response.text
    match = finish(client, response.json()["id"])
    assert match["status"] == "finished"
    assert match["seats"]["p1"] == {
        "name": "Vendor: acme/plays",
        "model_id": "acme/plays",
        "kind": "model",
    }
    assert {(player, model) for _, player, model in calls(database_url)} == {
        ("p1", "acme/plays"),
        ("p2", "glm-flash"),
    }
    assert sent["model"] in ("openrouter/acme/plays", "openrouter/" + "z-ai/glm-5.3-flash")


def test_an_id_in_no_catalog_is_refused_and_says_where_to_look(client, monkeypatch, answer_with):
    serve(monkeypatch)
    sent = answer_with(**PLAY_3)

    response = client.post(
        "/matches",
        json={"game": "toy", "models": ["acme/no-tools", "glm-flash"], "confirm_spend": True},
    )

    assert response.status_code == 422
    assert "Unknown model acme/no-tools" in response.json()["detail"]
    assert "GET /models/catalog" in response.json()["detail"]
    assert (sent, client.get("/matches").json()) == ({}, [])


def test_the_command_seats_a_catalog_model_too(database_url, monkeypatch, answer_with, capsys):
    serve(monkeypatch)
    answer_with(**PLAY_3)
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("OPENROUTER_API_KEY", KEY)

    code, output, complaints = arena(
        capsys, "run", "--game", "toy", "--models", "acme/plays,glm-flash"
    )

    assert (code, complaints) == (0, "")
    assert {model for _, _, model in calls(database_url)} == {"acme/plays", "glm-flash"}
