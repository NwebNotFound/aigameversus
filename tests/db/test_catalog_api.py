"""GET /models/catalog and model seats for models outside config/models.yaml.

OpenRouter's list is the sample of tests/test_catalog.py; LiteLLM answers from
its own mock with every name lookup refused. Nothing costs money.
"""

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

import arena.catalog as catalog
from arena.agents.model import ModelError
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
    assert models["glm-flash"]["price_source"] == "config/models.yaml"
    assert plays["price_source"] == "openrouter list"
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


def test_an_unverified_model_is_estimated_at_the_price_it_is_booked_at(client, monkeypatch):
    serve(monkeypatch)
    body = {"game": "toy", "models": ["acme/plays", "acme/plays"]}

    booked = client.post("/matches/estimate", json=body).json()
    client.app.state.estimates.answers.clear()
    monkeypatch.setattr(catalog, "UNVERIFIED_PRICE_MARGIN", Decimal(1))
    listed = client.post("/matches/estimate", json=body).json()

    assert booked["estimate_micro_eur"] == pytest.approx(
        1.25 * listed["estimate_micro_eur"], rel=0.01
    )
    assert booked["high_price"] == []


def test_an_estimate_names_the_models_that_cost_a_lot(client, monkeypatch):
    serve(monkeypatch)

    out = client.post(
        "/matches/estimate", json={"game": "toy", "models": ["acme/pricey", "glm-flash"]}
    )

    assert out.status_code == 200, out.text
    assert out.json()["high_price"] == ["acme/pricey"]


def test_an_estimate_refuses_an_id_in_no_catalog(client, monkeypatch):
    serve(monkeypatch)

    out = client.post(
        "/matches/estimate", json={"game": "toy", "models": ["acme/no-tools", "glm-flash"]}
    )

    assert out.status_code == 422
    assert "GET /models/catalog" in out.json()["detail"]


def test_free_variants_are_left_out_unless_asked_for(client, monkeypatch):
    serve(monkeypatch)

    plain = {m["id"] for m in client.get("/models/catalog").json()["models"]}
    with_free = client.get("/models/catalog", params={"free": 1}).json()["models"]

    assert "acme/gratis:free" not in plain
    gratis = next(m for m in with_free if m["id"] == "acme/gratis:free")
    assert gratis["rate_limited_likely"] is True and gratis["free"] is True
    assert all(not m["rate_limited_likely"] for m in with_free if m["id"] != "acme/gratis:free")


def test_a_model_whose_seat_gave_up_is_marked_unreliable_and_says_why(client, monkeypatch):
    serve(monkeypatch)
    answer_with_error = ModelError("AuthenticationError", retryable=False)
    monkeypatch.setattr(
        "arena.agents.budget.LiteLLMModel.__call__",
        lambda self, messages, tools: (_ for _ in ()).throw(answer_with_error),
    )

    started = client.post(
        "/matches",
        json={"game": "toy", "models": ["acme/plays", "glm-flash"], "confirm_spend": True},
    )
    finish(client, started.json()["id"])
    client.app.state.reliability = None  # the verdicts are kept for a minute
    models = {m["id"]: m for m in client.get("/models/catalog").json()["models"]}

    plays = models["acme/plays"]["reliability"]
    assert plays["status"] == "unreliable"
    assert "gave up in 1 of its last 2 matches" in plays["reason"]
    assert plays["agent_failed_recent"] == 1
    assert models["acme/thinks"]["reliability"]["status"] == "unknown"  # never played here


def test_a_seat_that_gave_up_three_matches_ago_no_longer_counts(client, monkeypatch, answer_with):
    serve(monkeypatch)
    body = {"game": "toy", "models": ["acme/plays", "glm-flash"], "confirm_spend": True}
    with monkeypatch.context() as broken:
        error = ModelError("AuthenticationError", retryable=False)
        broken.setattr(
            "arena.agents.budget.LiteLLMModel.__call__",
            lambda self, messages, tools: (_ for _ in ()).throw(error),
        )
        finish(client, client.post("/matches", json=body).json()["id"])
    answer_with(**PLAY_3)
    for _ in range(2):
        finish(client, client.post("/matches", json=body).json()["id"])
    client.app.state.reliability = None

    models = client.get("/models/catalog").json()["models"]
    plays = next(m for m in models if m["id"] == "acme/plays")["reliability"]

    assert plays["agent_failed_recent"] == 0
    assert plays["status"] == "unknown"  # too few moves for a verdict; the old failure is gone
