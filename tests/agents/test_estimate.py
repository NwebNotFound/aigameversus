"""The cost estimate: bots play, prompts are measured, nothing is called."""

import asyncio

import pytest

from arena.agents import estimate as estimating
from arena.agents.budget import cost_micro_eur
from arena.config import load_config
from games.poker.plugin import Poker
from games.toy.plugin import ToyGame

CONFIG = load_config()
SEATS = {"p1": "glm-flash", "p2": "deepseek-flash"}


def run(plugin, seats=SEATS, settings=None, history=None):
    return asyncio.run(estimating.estimate(plugin, seats, settings or {}, CONFIG, history or {}))


def test_every_seat_gets_its_prompts_priced_and_the_estimate_is_repeatable():
    first = run(ToyGame())

    assert set(first) == {"p1", "p2"}
    for seat, model_id in SEATS.items():
        assert first[seat].model_id == model_id
        assert first[seat].calls > 0 and first[seat].estimate_micro_eur > 0
    assert run(ToyGame()) == first


def test_a_model_with_history_is_counted_at_its_mean_output_else_at_the_limit():
    many = (estimating.HISTORY_MIN, 100.0)
    few = (estimating.HISTORY_MIN - 1, 100.0)

    known = run(ToyGame(), history={"glm-flash": many, "deepseek-flash": many})
    unknown = run(ToyGame(), history={"glm-flash": few, "deepseek-flash": few})

    assert all(known[s].estimate_micro_eur < unknown[s].estimate_micro_eur for s in SEATS)
    calls = known["p1"].calls
    output_only = cost_micro_eur(
        CONFIG, CONFIG.models["glm-flash"], 0, calls * 100.0 * estimating.RETRY_SHARE
    )
    assert known["p1"].estimate_micro_eur > output_only  # plus the prompts


def test_the_prompt_version_of_the_settings_is_measured():
    seats = {"p1": "glm-flash", "p2": "glm-flash", "p3": "glm-flash"}
    p1 = run(Poker(), seats, {"hand_limit": 3})
    p2 = run(Poker(), seats, {"hand_limit": 3, "prompt_version": "poker-p2"})

    assert [p1[s].calls for s in seats] == [p2[s].calls for s in seats]  # the same bot play
    assert all(p2[s].estimate_micro_eur > p1[s].estimate_micro_eur for s in seats)  # longer


def test_a_player_count_the_game_refuses_is_a_value_error():
    with pytest.raises(ValueError, match="players"):
        run(ToyGame(), {"p1": "glm-flash"})


def test_the_summary_a_model_would_read_is_measured():
    class Summarised(ToyGame):
        def rules(self, settings=None):
            return ToyGame().rules()

        def situation_summary(self, observation, settings=None):
            return "x" * 20_000

    plain, summarised = run(ToyGame()), run(Summarised())

    for seat in SEATS:
        assert summarised[seat].calls == plain[seat].calls
        assert summarised[seat].estimate_micro_eur > plain[seat].estimate_micro_eur


def test_each_seat_is_estimated_at_its_most_expensive_trial_match(monkeypatch):
    single = {}
    for seed in estimating.SEEDS:
        monkeypatch.setattr(estimating, "SEEDS", (seed,))
        single[seed] = run(Poker(), {p: "glm-flash" for p in ("p1", "p2", "p3")})
    monkeypatch.undo()

    combined = run(Poker(), {p: "glm-flash" for p in ("p1", "p2", "p3")})

    for seat, got in combined.items():
        costs = [single[seed][seat].estimate_micro_eur for seed in single]
        assert got.estimate_micro_eur == max(costs)
        assert len(set(costs)) > 1  # the trial matches differ, so the choice matters


def test_the_estimate_counts_the_wider_event_history_of_a_game_that_asks_for_it():
    """Civ shows 120 events a prompt (D-136): the free estimate that gates a run must price them."""
    from games.civ.plugin import CivGame

    class NarrowCiv(CivGame):
        def history_limit(self, settings=None):
            return 40

    nations = {f"p{i}": "glm-flash" for i in range(1, 5)}
    settings = {"rounds": 20}

    wide = run(CivGame(), nations, settings)
    narrow = run(NarrowCiv(), nations, settings)

    assert CivGame().history_limit(settings) == 120
    assert all(wide[s].estimate_micro_eur > narrow[s].estimate_micro_eur for s in nations)
    assert wide["p1"].calls == narrow["p1"].calls  # the same turns, longer prompts


def test_a_game_with_the_default_window_is_priced_as_before():
    class Explicit(ToyGame):
        def history_limit(self, settings=None):
            return 40

        def rules(self, settings=None):  # rules.md lives next to ToyGame, not here
            return ToyGame().rules(settings)

    assert ToyGame().history_limit({}) == 40
    assert run(Explicit()) == run(ToyGame())
