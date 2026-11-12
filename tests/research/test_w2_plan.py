import asyncio
from collections import Counter
from pathlib import Path

import pytest
import yaml

from arena.agents.random_bot import random_bots
from arena.engine.match import Match
from arena.research.guest_schedule import rows
from games.werewolf.plugin import Werewolf


@pytest.fixture
def plan():
    root = Path(__file__).resolve().parents[2]
    return yaml.safe_load((root / "research/W2/PLAN.yaml").read_text())


def test_fixed_hosts_two_role_cells_and_no_omitted_models(plan):
    schedule = rows(plan)
    assert len(schedule) == plan["max_matches"] == 8
    assert rows(plan) == schedule
    counts = Counter(row["guest"] for row in schedule)
    assert set(counts.values()) == {2}
    assert len({row["guest"] for row in schedule[:4]}) == 4
    for row in schedule:
        assert row[row["guest_seat"]] == row["guest"]
        assert row["expected_role"] == plan["expected_roles"][row["guest_seat"]]
        hosts = [row[f"p{i}"] for i in range(1, 9) if f"p{i}" != row["guest_seat"]]
        assert hosts == plan["hosts_in_fixed_relative_order"]
        assert not set(hosts).intersection(plan["excluded_hosts"])


def test_role_fixture_uses_only_random_bots_and_matches_deployed_seed_contract(plan):
    game = Werewolf()
    players = [f"p{i}" for i in range(1, 9)]
    match = Match(
        game, random_bots(game, players, plan["seed"]), seed=plan["seed"], settings=plan["settings"]
    )
    asyncio.run(match.run())
    assert match.state.roles == plan["expected_roles"]


def test_execution_has_exact_approval_without_increasing_allocation(plan):
    assert plan["execution_plan_approved"] is True
    assert "e460648f-4457-409f-abcc-91d58f14887c" in plan["execution_approval_evidence"]
    assert "Reviewer live-state confirmation required" in plan["execution_approval_evidence"]
    assert plan["memory"] is False
    assert plan["settings"]["prompt_version"] == "werewolf-p2"
    assert any("#144 merged" in item for item in plan["prerequisites"])
    assert all(quote < 400_000 for quote in plan["free_quotes_micro_eur"].values())
    assert plan["settings"]["answer_repair"] == "off"
    assert plan["budget"]["stage_eur"] == 3.50
    assert plan["settings"]["match_budget_eur"] == plan["budget"]["match_cap_eur"] == 0.40
    assert plan["max_matches"] * plan["budget"]["match_cap_eur"] <= plan["budget"]["stage_eur"]
    assert len(plan["prerequisites"]) == len(set(plan["prerequisites"]))
    assert 2 * sum(plan["free_quotes_micro_eur"].values()) / 1_000_000 == pytest.approx(
        plan["budget"]["estimated_eight_matches_eur"]
    )
