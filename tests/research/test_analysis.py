"""The registered E1 analysis: known values for each test, and a run folder of bot matches."""

import asyncio
import json
import random

import pytest

from arena.agents.random_bot import random_bots
from arena.engine.match import Match
from arena.games import load_games
from arena.research.analysis import (
    analyse,
    binomial_two_sided,
    fisher_two_sided,
    h1_permutation,
    holm,
    mantel_haenszel,
    plackett_luce,
    wilson,
)


def test_binomial_two_sided_matches_counting():
    assert binomial_two_sided(0, 10, 0.5) == pytest.approx(2 / 1024)
    assert binomial_two_sided(5, 10, 0.5) == pytest.approx(1.0)
    assert binomial_two_sided(1, 10, 0.5) == pytest.approx(22 / 1024)


def test_fisher_matches_the_tea_tasting_table():
    # Fisher's lady tasting tea: 3 of 4 right, two-sided p = 34/70.
    assert fisher_two_sided(3, 1, 1, 3) == pytest.approx(34 / 70)
    assert fisher_two_sided(4, 0, 0, 4) == pytest.approx(2 / 70)


def test_mantel_haenszel_of_one_table_is_its_odds_ratio():
    result = mantel_haenszel([(10, 5, 5, 10)])
    assert result["odds_ratio"] == pytest.approx(4.0)
    # By hand: E = 7.5, V = 15^4 / (30^2 * 29), chi2 = (2.5 - 0.5)^2 / V = 2.0622.
    assert result["chi2"] == pytest.approx(2.0622, abs=1e-3)
    assert mantel_haenszel([(5, 5, 5, 5)])["p"] > 0.5


def test_holm_adjusts_in_order_and_stays_monotone():
    assert holm({"a": 0.01, "b": 0.04, "c": 0.03}) == pytest.approx(
        {"a": 0.03, "c": 0.06, "b": 0.06}
    )


def test_wilson_interval_of_known_cases():
    # Textbook values: 0 of 10 has upper end 0.2775; 5 of 10 is 0.2366 to 0.7634.
    assert wilson(0, 10) == pytest.approx((0.0, 0.2775), abs=1e-4)
    assert wilson(5, 10) == pytest.approx((0.2366, 0.7634), abs=1e-4)
    assert wilson(0, 0) is None


def test_plackett_luce_recovers_a_planted_order():
    rng = random.Random(1)
    true = {"a": 3.0, "b": 2.0, "c": 1.0, "d": 0.5, "e": 0.25, "f": 0.1}
    rankings = []
    for _ in range(400):
        table = rng.sample(sorted(true), 4)
        ranking = []
        while table:
            weights = [true[i] for i in table]
            pick = rng.choices(table, weights)[0]
            ranking.append(pick)
            table.remove(pick)
        rankings.append(ranking)

    strengths = plackett_luce(rankings)

    assert sorted(strengths, key=lambda i: -strengths[i]) == ["a", "b", "c", "d", "e", "f"]
    assert sum(strengths.values()) == pytest.approx(0.0, abs=1e-9)


def _match(seats, ranks, seed=1):
    return {"seats": seats, "ranks": ranks, "seed": seed}


def test_h1_finds_a_model_that_always_wins_and_not_random_ranks():
    seats = {"p1": "a", "p2": "b", "p3": "c", "p4": "d"}
    strong = [_match(seats, {"p1": 1, "p2": 2, "p3": 3, "p4": 4}) for _ in range(30)]
    assert h1_permutation(strong, permutations=500)["p"] < 0.01

    rng = random.Random(3)
    noise = []
    for _ in range(30):
        ranks = [1, 2, 3, 4]
        rng.shuffle(ranks)
        noise.append(_match(seats, dict(zip(seats, ranks, strict=True))))
    assert h1_permutation(noise, permutations=500)["p"] > 0.05


def _bot_run(tmp_path, count=12):
    """A run folder as the batch runner writes it, from free random-bot matches."""
    plugin = load_games()["liars_deck"]
    models = ["m1", "m2", "m3", "m4", "m5", "m6"]
    lines = []
    for order in range(1, count + 1):
        names = random.Random(order).sample(models, 4)
        players = ["p1", "p2", "p3", "p4"]
        events = []

        async def sink(first, new, events=events):
            for offset, event in enumerate(new):
                events.append({"seq": first + offset, **event.model_dump(mode="json")})

        seed = 1000 + order
        placements = asyncio.run(
            Match(plugin, random_bots(plugin, players, seed), sink=sink, seed=seed).run()
        )
        (tmp_path / f"{order:03d}.json").write_text(
            json.dumps({"record": {}, "cost": {}, "events": events}), encoding="utf-8"
        )
        lines.append(
            {
                "order": order,
                "stage": "A2",
                "table": "T01",
                "seating": 1,
                "replicate": 1,
                "seed": seed,
                "pilot": False,
                "match_id": f"m{order}",
                "status": "finished",
                "cost_micro_eur": 1000,
                "attempt": 1,
                "placements": [p.model_dump() for p in placements],
                "seats": {
                    p: {
                        "model": m,
                        "turns": 10,
                        "fallbacks": 0,
                        "rejected": 0,
                        "agent_failed": False,
                    }
                    for p, m in zip(players, names, strict=True)
                },
                "prompt_version": "liars_deck-p1",
            }
        )
    (tmp_path / "runs.jsonl").write_text(
        "".join(json.dumps(line) + "\n" for line in lines), encoding="utf-8"
    )
    return tmp_path


def test_analyse_runs_end_to_end_on_a_folder_of_bot_matches(tmp_path):
    result = analyse(_bot_run(tmp_path), permutations=200, resamples=50)

    assert result["design"]["matches"] == 12
    assert set(result["H2"]) <= {"m1", "m2", "m3", "m4", "m5", "m6"}
    assert sum(r["wins"] for r in result["H2"].values()) == 12
    assert sum(result["H4"]["wins_by_seat"]) == 12
    assert 0 < result["H1"]["p"] <= 1
    tables = [row["table"] for row in result["H3"]["per_model"].values()]
    assert all(sum(t) > 0 for t in tables)  # random bots call and play, facing lies and truths
    assert all(r["clean_share"] == 1.0 for r in result["reliability"].values())
    assert set(result["plackett_luce"]) == set(result["H2"])


def test_the_same_run_gives_the_same_numbers(tmp_path):
    run = _bot_run(tmp_path, count=6)
    assert analyse(run, permutations=100, resamples=20) == analyse(
        run, permutations=100, resamples=20
    )
