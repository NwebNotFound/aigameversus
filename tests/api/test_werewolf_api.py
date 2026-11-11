from fastapi.testclient import TestClient

from arena.api.app import app

client = TestClient(app)


def test_roles_lists_every_role_with_its_selection_fields():
    response = client.get("/games/werewolf/roles")

    assert response.status_code == 200
    roles = {role["id"]: role for role in response.json()}
    assert len(roles) == 16
    assert roles["seer"] == {
        "id": "seer",
        "name": "Seherin",
        "team": "village",
        "unique": True,
        "weight": 7,
        "night_order": roles["seer"]["night_order"],
        "first_night_only": False,
        "description": roles["seer"]["description"],
    }


def test_valid_selection_comes_back_filled_with_balance():
    response = client.post(
        "/games/werewolf/selection/validate",
        json={"roles": {"werewolf": 2, "seer": 1, "witch": 1}, "player_count": 8},
    )

    assert response.status_code == 200
    assert response.json() == {
        "valid": True,
        "problems": [],
        "selection": {"werewolf": 2, "seer": 1, "witch": 1, "villager": 4},
        "balance": {"total": 3, "verdict": "even"},
    }


def test_invalid_selection_lists_its_problems():
    response = client.post(
        "/games/werewolf/selection/validate",
        json={"roles": {"seer": 2}, "player_count": 8},
    )

    body = response.json()
    assert response.status_code == 200
    assert body["valid"] is False
    assert [(p["code"], p["role"]) for p in body["problems"]] == [
        ("unique_role_repeated", "seer"),
        ("no_wolf", None),
    ]
    assert body["problems"][0]["message"] == "Seherin may appear only once, selected 2 times"
    assert body["balance"] == {"total": 20, "verdict": "village"}


def test_unknown_role_has_no_balance():
    response = client.post(
        "/games/werewolf/selection/validate",
        json={"roles": {"werewolf": 1, "vampire": 1}, "player_count": 8},
    )

    body = response.json()
    assert body["problems"][0]["code"] == "unknown_role"
    assert body["balance"] is None


def test_malformed_request_is_a_422():
    response = client.post(
        "/games/werewolf/selection/validate",
        json={"roles": {"werewolf": "two"}, "player_count": 8},
    )

    assert response.status_code == 422
