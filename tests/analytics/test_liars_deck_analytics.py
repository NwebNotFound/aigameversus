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
    # No risk at a pull: it needs the hidden revolver loading.
    assert all(pull["risk"] is None for pull in open_["pulls"])
    # Hidden events are not even read.
    hidden = {seq for seq, e in enumerate(events) if e.visible_to is not None}
    assert not hidden & {m["seq"] for m in open_["moves"]}
    assert open_["events"] == len(events) - len(hidden)
    assert "thought" not in json.dumps(open_)


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


def test_risk_at_a_pull_is_live_chambers_over_chambers_left():
    analytics = match_analytics("liars_deck", played(9), spoilers=True)

    for pull in analytics["pulls"]:
        assert 0 < pull["risk"] <= 1
        if pull["pull"] == 1:
            assert pull["risk"] == pytest.approx(1 / 6)  # one live chamber of six at the start


def test_a_real_match_has_its_fallbacks_and_a_partial_log_works():
    events = example()

    full = match_analytics("liars_deck", events, spoilers=True)
    partial = match_analytics("liars_deck", events[:60], spoilers=True)

    assert full["totals"]["p3"]["fallbacks"] >= 1
    assert 0 < len(partial["moves"]) < len(full["moves"])
    # Without the decision fields yet, thinking time is unknown, not 0.
    assert all(m["latency_ms"] is None for m in full["moves"])
    assert full["totals"]["p1"]["thinking_ms_total"] is None


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
    assert total["thinking_ms_total"] == 1200 * len(mine)
    assert total["tokens_out"] == 40 * len(mine)


def test_the_same_log_gives_the_same_analytics():
    events = played(11)

    assert match_analytics("liars_deck", events, True) == match_analytics(
        "liars_deck", events, True
    )


def test_a_game_without_analytics_says_so():
    with pytest.raises(NoAnalytics, match="No analytics for toy yet"):
        match_analytics("toy", [], spoilers=True)
