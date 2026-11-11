"""Liar's Deck analytics: per move, per player and per round, with and without spoilers."""

import asyncio
import json
from pathlib import Path

import pytest

from arena.agents.random_bot import random_bots
from arena.analytics import NoAnalytics, match_analytics
from arena.engine.match import Match
from arena.engine.types import Event
from arena.games import load_games
from arena.stats import STATS

EXAMPLE = Path(__file__).resolve().parents[2] / "docs" / "examples" / "liars_deck.json"


def played(seed, players=4, settings=None):
    plugin = load_games()["liars_deck"]
    seats = [f"p{i}" for i in range(1, players + 1)]
    match = Match(plugin, random_bots(plugin, seats, seed), seed=seed, settings=settings or {})
    asyncio.run(match.run())
    return match.events


def example():
    data = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    return [Event(**{k: v for k, v in e.items() if k != "seq"}) for e in data["events"]]


@pytest.mark.parametrize("seed", [1, 2, 3, 4, 5])
def test_with_spoilers_the_totals_agree_with_the_statistics(seed):
    events = played(seed)

    totals = match_analytics("liars_deck", events, spoilers=True)["totals"]

    stats = STATS["liars_deck"].match_stats(events)
    for player, mine in totals.items():
        theirs = stats[player]
        assert mine["plays"] == mine["plays_known"] == theirs.plays
        assert mine["lies"] == theirs.lies
        assert mine["lies_called"] == theirs.times_caught
        assert (mine["calls"], mine["calls_correct"]) == (theirs.calls, theirs.calls_correct)


@pytest.mark.parametrize("events", [played(6), example()], ids=["bot match", "real models"])
def test_without_spoilers_nothing_hidden_is_counted(events):
    open_ = match_analytics("liars_deck", events, spoilers=False)
    full = match_analytics("liars_deck", events, spoilers=True)

    # Only revealed plays have an honesty, and they agree with the full view.
    full_by_seq = {m["seq"]: m for m in full["moves"]}
    for move in open_["moves"]:
        if move["kind"] == "play":
            assert move["honest"] is None or move["called"]
            if move["honest"] is not None:
                assert move["honest"] == full_by_seq[move["seq"]]["honest"]
    # Risk needs no secret: the same in both views.
    assert [p["risk"] for p in open_["pulls"]] == [p["risk"] for p in full["pulls"]]
    # Hidden events are not read, except the start without its seed and secret settings.
    hidden = {
        seq
        for seq, e in enumerate(events)
        if e.visible_to is not None and e.type != "match_started"
    }
    assert not hidden & {m["seq"] for m in open_["moves"]}
    assert open_["events"] == len(events) - len(hidden)
    assert "thought" not in json.dumps(open_)
    assert open_["meta"]["seed"] is None


def test_every_move_points_at_its_event_in_the_log():
    events = played(7)

    analytics = match_analytics("liars_deck", events, spoilers=True)

    kinds = {"play": "cards_played", "call": "liar_called"}
    for move in analytics["moves"]:
        assert events[move["seq"]].type == kinds[move["kind"]]
    for pull in analytics["pulls"]:
        assert events[pull["seq"]].type == "trigger_pulled"
    assert [m["index"] for m in analytics["moves"]] == list(range(len(analytics["moves"])))


def test_by_round_adds_up_to_the_totals():
    analytics = match_analytics("liars_deck", played(8), spoilers=True)

    for player, total in analytics["totals"].items():
        cells = [r["players"][player] for r in analytics["by_round"]]
        assert sum(c["lies"] for c in cells) == total["lies"]
        assert sum(c["honest"] for c in cells) == total["honest"]
        assert sum(c["calls"] for c in cells) == total["calls"]


def test_risk_is_live_chambers_over_chambers_left_and_needs_no_spoilers():
    events = played(9)

    for spoilers in (True, False):
        analytics = match_analytics("liars_deck", events, spoilers=spoilers)
        for pull in analytics["pulls"]:
            # The pull-th pull has 6 - (pull - 1) chambers left, one of them live.
            assert pull["risk"] == pytest.approx(1 / (6 - pull["pull"] + 1))
        for move in analytics["moves"]:
            assert 0 < move["risk"] <= 1


def test_a_real_match_has_its_fallbacks_and_a_partial_log_works():
    events = example()

    full = match_analytics("liars_deck", events, spoilers=True)
    partial = match_analytics("liars_deck", events[:60], spoilers=True)

    assert full["totals"]["p3"]["fallbacks"] >= 1
    assert 0 < len(partial["moves"]) < len(full["moves"])
    # Without the decision fields yet, thinking time is unknown, not 0.
    assert all(m["latency_ms"] is None for m in full["moves"])
    assert full["totals"]["p1"]["response_ms_total"] is None


def test_thinking_time_is_read_from_the_decision_event_when_present():
    events = played(10)
    for event in events:
        if event.type == "action_accepted":
            event.data.update(latency_ms=1200, tokens_in=900, tokens_out=40)

    analytics = match_analytics("liars_deck", events, spoilers=True)

    moves = [m for m in analytics["moves"] if not (m["kind"] == "call" and m["automatic"])]
    assert all(m["latency_ms"] == 1200 for m in moves)
    total = analytics["totals"]["p1"]
    mine = [m for m in moves if m["player"] == "p1"]
    assert total["response_ms_total"] == 1200 * len(mine)
    assert total["tokens_out"] == 40 * len(mine)


def test_the_same_log_gives_the_same_analytics():
    events = played(11)

    assert match_analytics("liars_deck", events, True) == match_analytics(
        "liars_deck", events, True
    )


def test_a_game_without_analytics_says_so():
    with pytest.raises(NoAnalytics, match="No analytics for toy yet"):
        match_analytics("toy", [], spoilers=True)


@pytest.mark.parametrize("seed", [12, 13, 14])
def test_a_lie_is_forced_exactly_when_the_hand_held_no_table_card(seed):
    events = played(seed)
    analytics = match_analytics("liars_deck", events, spoilers=True)

    for move in analytics["moves"]:
        if move["kind"] != "play":
            continue
        assert move["table_cards_held"] is not None
        if move["honest"] is False:
            assert move["forced"] == (move["table_cards_held"] == 0)
            assert 0 < move["lie_size"] <= 1
            assert move["false_cards"] == round(move["lie_size"] * move["cards"])
        else:
            assert move["forced"] is None and move["false_cards"] == 0


def test_every_rate_carries_its_n_and_no_data_is_null():
    totals = match_analytics("liars_deck", played(15), spoilers=True)["totals"]

    for total in totals.values():
        lie = total["lie_rate"]
        assert (lie["n"], lie["of"]) == (total["lies"], total["plays_known"])
        assert lie["value"] == (None if lie["of"] == 0 else lie["n"] / lie["of"])
        chosen = total["chosen_lie_rate"]
        assert chosen["n"] == total["lies"] - total["forced_lies"]
        for name in ("call_rate", "hit_rate", "false_alarm_rate", "call_accuracy"):
            assert total[name]["n"] <= total[name]["of"]


def test_opportunities_split_into_ones_facing_a_lie_and_ones_facing_the_truth():
    analytics = match_analytics("liars_deck", played(16, players=3), spoilers=True)

    for total in analytics["totals"].values():
        calls_on_lies = total["hit_rate"]["n"]
        calls_on_truth = total["false_alarm_rate"]["n"]
        assert calls_on_lies + calls_on_truth == total["calls"]
        assert total["hit_rate"]["of"] + total["false_alarm_rate"]["of"] == total["call_rate"]["of"]
        assert calls_on_lies == total["calls_correct"]


def test_fallback_moves_are_flagged_and_left_out_of_the_skill_numbers():
    events = example()
    analytics = match_analytics("liars_deck", events, spoilers=True)

    p3 = analytics["totals"]["p3"]
    flagged = [m for m in analytics["moves"] if m["player"] == "p3" and m["fallback"]]
    own_plays = [
        m
        for m in analytics["moves"]
        if m["player"] == "p3" and m["kind"] == "play" and not m["fallback"]
    ]
    assert flagged and p3["fallbacks"] == len(flagged)
    assert p3["plays"] == len(own_plays)
    assert p3["fallback_share"]["n"] == len(flagged)


def test_without_spoilers_the_numbers_that_need_hidden_cards_are_null():
    totals = match_analytics("liars_deck", played(17), spoilers=False)["totals"]

    for total in totals.values():
        for name in (
            "lie_rate",
            "chosen_lie_rate",
            "forced_lies",
            "mean_lie_size",
            "hit_rate",
            "false_alarm_rate",
        ):
            assert total[name] is None
        assert total["call_rate"]["of"] >= total["calls"]


def test_the_match_says_what_it_was_for_grouping():
    meta = match_analytics("liars_deck", example(), spoilers=True)["meta"]
    public = match_analytics("liars_deck", example(), spoilers=False)["meta"]

    assert meta["version"] == "1" and meta["seed"] == 2027 and meta["settings"] == {}
    assert public["seed"] is None and public["version"] == "1"


def test_the_spoiler_free_start_keeps_only_the_public_settings():
    events = played(18, settings={"variant": "devil_card"})
    for event in events:
        if event.type == "match_started":
            event.data["settings"]["secret_test_setting"] = "hidden"

    public = match_analytics("liars_deck", events, spoilers=False)

    assert public["meta"]["settings"] == {"variant": "devil_card"}
    assert "hidden" not in json.dumps(public)


@pytest.mark.parametrize("events", [played(8), example()], ids=["bot match", "real models"])
def test_the_round_cells_add_up_to_the_totals_and_leave_fallbacks_out(events):
    analytics = match_analytics("liars_deck", events, spoilers=True)

    for player, total in analytics["totals"].items():
        cells = [r["players"][player] for r in analytics["by_round"]]
        assert sum(c["lies"] for c in cells) == total["lies"]
        assert sum(c["honest"] for c in cells) == total["honest"]
        assert sum(c["calls"] for c in cells) == total["calls"]
        assert sum(c["fallbacks"] for c in cells) == total["fallbacks"]
    # The real example has random-bot moves of p3: they are counted, but only as fallbacks.
    if analytics["totals"]["p3"]["fallbacks"]:
        p3 = [r["players"]["p3"] for r in analytics["by_round"]]
        assert sum(c["lies"] + c["calls"] for c in p3) == (
            analytics["totals"]["p3"]["lies"] + analytics["totals"]["p3"]["calls"]
        )
