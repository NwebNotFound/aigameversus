"""The Throne of Tokens balance sweep: bot matches summed up from their logs."""

from arena.research import civ_balance


def test_a_match_is_summed_up_from_its_log_and_the_same_seed_gives_the_same_numbers():
    first = civ_balance.play(4, 5, seed=1)

    assert first == civ_balance.play(4, 5, seed=1)
    assert first["nations"] == 4 and first["rounds"] <= 5
    assert first["kind"] in ("round_limit", "domination", "economy")
    assert sorted(first["rank_by_seat"]) == ["p1", "p2", "p3", "p4"]
    assert set(first["scarce_by_seat"]) == {"p1", "p2", "p3", "p4"}
    assert 0 <= first["refused"] <= first["orders"]


def test_a_table_counts_every_match_and_renders_as_markdown():
    tables = civ_balance.sweep(2, nations=(4,), lengths=(5,))

    t = tables["4x5"]
    assert t["matches"] == 2 and sum(t["victory"].values()) == 2
    assert sum(t["wins_by_seat"].values()) >= 2  # shared first places count for each
    assert set(t["rank_mean_by_seat"]) == {"p1", "p2", "p3", "p4"}
    text = civ_balance.markdown(tables)
    assert "| 4x5 | 2 |" in text and "start region short of" in text
