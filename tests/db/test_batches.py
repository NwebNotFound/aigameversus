"""Batches: a match started in one carries it, lists filter by it, old matches are tagged later."""

import json
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from arena import cli
from arena.api.app import app
from tests.db.test_matches_api import follow

LEAGUE = {
    "id": "E1-A2",
    "label": "E1 league A2 (6 models, Liar's Deck)",
    "index": 14,
    "of": 120,
    "budget_eur": 3.0,
}


@pytest.fixture
def client(database_url, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", database_url)
    with TestClient(app) as client:
        yield client


def start(client, **body):
    response = client.post("/matches", json={"game": "toy", **body})
    assert response.status_code == 201, response.text
    return response.json()


def test_a_match_started_in_a_batch_carries_it_and_the_list_filters_by_it(client):
    tagged = start(client, seed=1, batch=LEAGUE)
    other = start(client, seed=2, batch={"id": "E9", "label": "another run"})
    alone = start(client, seed=3)

    assert tagged["batch"] == LEAGUE
    assert client.get(f"/matches/{tagged['id']}").json()["batch"] == LEAGUE
    assert other["batch"] == {
        "id": "E9",
        "label": "another run",
        "index": None,
        "of": None,
        "budget_eur": None,
    }
    assert alone["batch"] is None
    listed = client.get("/matches", params={"batch": "E1-A2"}).json()
    assert [match["id"] for match in listed] == [tagged["id"]]
    assert {m["id"] for m in client.get("/matches").json()} >= {tagged["id"], alone["id"]}
    assert client.get("/matches", params={"batch": "nope"}).json() == []


@pytest.mark.parametrize(
    "batch",
    [
        {**LEAGUE, "replicate": 2},  # unknown key: a typo fails loudly
        {**LEAGUE, "index": 121},
        {**LEAGUE, "index": 0},
        {**LEAGUE, "id": "has space"},
        {**LEAGUE, "label": ""},
        {**LEAGUE, "budget_eur": -1},
        {"label": "no id"},
    ],
)
def test_a_bad_batch_is_refused_and_starts_nothing(client, batch):
    response = client.post("/matches", json={"game": "toy", "batch": batch})

    assert response.status_code == 422
    assert client.get("/matches").json() == []


def started_file(tmp_path, lines):
    path = tmp_path / "started.jsonl"
    path.write_text("".join(json.dumps(line) + "\n" for line in lines), encoding="utf-8")
    return path


def test_a_batch_summary_counts_its_matches_by_status_and_adds_up_their_cost(client):
    done = start(client, seed=1, batch={**LEAGUE, "index": 1})
    start(client, seed=2, batch={**LEAGUE, "index": 2}, turn_delay=5)
    follow(client, done["id"])  # the stream closes when the match has stopped

    summary = client.get("/batches/E1-A2").json()

    assert {k: summary[k] for k in ("id", "label", "of", "budget_eur", "matches")} == {
        "id": "E1-A2",
        "label": LEAGUE["label"],
        "of": 120,
        "budget_eur": 3.0,
        "matches": 2,
    }
    assert summary["statuses"] == {"finished": 1, "running": 1}
    assert summary["cost_micro_eur"] == 0  # bots cost nothing
    assert client.get("/batches/nope").status_code == 404


def backfill(path, *extra, of=120, first=113):
    args = ["batches", "backfill", str(path), "--id", "E1-A2", "--label", LEAGUE["label"]]
    return cli.main([*args, "--of", str(of), "--first-order", str(first), *extra])


def test_backfill_tags_played_matches_by_their_order_and_a_second_run_changes_nothing(
    client, tmp_path, capsys
):
    first, replayed, again = start(client, seed=1), start(client, seed=2), start(client, seed=3)
    path = started_file(
        tmp_path,
        [
            {"order": 113, "match_id": first["id"]},
            {"order": 126, "match_id": replayed["id"]},
            {"order": 126, "match_id": again["id"]},  # the same cell played again: both tagged
        ],
    )

    assert backfill(path) == 0
    assert "Tagged 3 match(es); 0 already in E1-A2." in capsys.readouterr().out
    batches = {m["id"]: m["batch"] for m in client.get("/matches?batch=E1-A2").json()}
    league = {**LEAGUE, "budget_eur": None}  # the backfill does not know the budget
    assert batches[first["id"]] == {**league, "index": 1}
    assert batches[replayed["id"]] == batches[again["id"]] == {**league, "index": 14}

    assert backfill(path) == 0
    assert "Tagged 0 match(es); 3 already in E1-A2." in capsys.readouterr().out


def test_backfill_never_moves_a_match_and_reports_what_it_left(client, tmp_path, capsys):
    elsewhere = start(client, seed=1, batch={"id": "E9", "label": "another run"})
    fine = start(client, seed=2)
    path = started_file(
        tmp_path,
        [
            {"order": 113, "match_id": elsewhere["id"]},
            {"order": 114, "match_id": str(uuid4())},
            {"order": 300, "match_id": fine["id"]},
            {"order": 115, "match_id": fine["id"]},
        ],
    )

    assert backfill(path) == 1

    out = capsys.readouterr().out
    assert "Tagged 1 match(es)" in out
    assert f"Not tagged: {elsewhere['id']}: already in another batch, left as it is" in out
    assert "no such match in this database" in out
    assert "order 300 is outside the batch" in out
    assert client.get(f"/matches/{elsewhere['id']}").json()["batch"]["id"] == "E9"
    assert client.get(f"/matches/{fine['id']}").json()["batch"]["index"] == 3


def test_backfill_with_the_schedule_tags_only_matches_whose_seed_fits_their_row(
    client, tmp_path, capsys
):
    right, wrong = start(client, seed=1101021), start(client, seed=7)
    schedule = tmp_path / "schedule.csv"
    schedule.write_text("order,stage,seed\n113,A2,1101021\n114,A2,1101022\n", encoding="utf-8")
    path = started_file(
        tmp_path,
        [{"order": 113, "match_id": right["id"]}, {"order": 114, "match_id": wrong["id"]}],
    )

    assert backfill(path, "--schedule", str(schedule)) == 1

    assert f"{wrong['id']}: seed 7, but order 114 of the schedule has 1101022" in (
        capsys.readouterr().out
    )
    assert client.get(f"/matches/{right['id']}").json()["batch"]["index"] == 1
    assert client.get(f"/matches/{wrong['id']}").json()["batch"] is None


def test_a_broken_log_line_stops_the_backfill_before_it_writes(client, tmp_path):
    match = start(client, seed=1)
    path = tmp_path / "started.jsonl"
    path.write_text(json.dumps({"order": 113, "match_id": match["id"]}) + "\nnot json\n")

    with pytest.raises(SystemExit):
        backfill(path)

    assert client.get(f"/matches/{match['id']}").json()["batch"] is None
