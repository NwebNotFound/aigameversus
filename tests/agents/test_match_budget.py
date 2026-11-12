"""settings.match_budget_eur: a match's own spend limit, only ever lower than the config's cap."""

import asyncio
from decimal import Decimal
from uuid import uuid4

import pytest

from arena.agents.budget import Budget
from arena.agents.random_bot import random_bots
from arena.config import Config, Limits
from arena.engine.match import Match
from arena.engine.types import match_budget_of
from games.poker.plugin import Poker
from games.toy.plugin import ToyGame


def config(match_eur="0.50"):
    return Config(
        limits=Limits(
            match_eur=Decimal(match_eur),
            month_eur=Decimal("25"),
            usd_to_eur=Decimal("1"),
            max_input_tokens=5000,
            max_output_tokens=100,
        ),
        models={},
    )


@pytest.mark.parametrize(
    ("limit", "cap"),
    [
        (None, 500_000),
        (Decimal("0.20"), 200_000),
        (Decimal("0.80"), 500_000),
        (Decimal("0.5"), 500_000),
    ],
)
def test_the_match_cap_is_the_lower_of_the_config_and_the_matchs_own_limit(limit, cap):
    budget = Budget(None, uuid4(), config(), match_eur=limit)

    assert budget.match_cap == cap
    assert budget.month_cap == 25_000_000  # the month is never touched


@pytest.mark.parametrize("value", ["0.2", 0, -0.1, True, None.__class__])
def test_a_limit_that_is_not_euros_above_zero_is_refused(value):
    with pytest.raises(ValueError, match="match_budget_eur"):
        Match(ToyGame(), {"p1": None, "p2": None}, seed=1, settings={"match_budget_eur": value})


def test_the_game_never_sees_the_limit_and_the_start_records_it():
    # Poker refuses every setting it does not know: this one must never reach it.
    match = Match(Poker(), {"p1": None, "p2": None}, seed=1, settings={"match_budget_eur": 0.2})

    assert match.settings == {"match_budget_eur": 0.2}
    assert match_budget_of(match.settings) == Decimal("0.2")
    assert match_budget_of({}) is None


@pytest.mark.parametrize("value", ["lots", "0.2", True, float("nan"), float("inf"), -1, 0])
def test_reading_a_limit_that_is_not_euros_names_the_setting(value):
    # The CLI reads the setting with match_budget_of: never a bare decimal error.
    with pytest.raises(ValueError, match="match_budget_eur"):
        match_budget_of({"match_budget_eur": value})


def test_the_game_sees_neither_engine_setting_and_the_start_records_both():
    plugin = Poker()  # refuses every setting it does not know
    settings = {"match_budget_eur": 0.2, "thought_headline": True}
    match = Match(plugin, random_bots(plugin, ["p1", "p2"], 1), seed=1, settings=settings)

    asyncio.run(match.run())

    (started,) = [e for e in match.events if e.type == "match_started"]
    assert started.data["settings"] == settings
    assert any(e.type == "match_finished" for e in match.events)
