"""The match report: at a glance, the ranking table and key moments, per game and view."""

import asyncio
import json
import re
from pathlib import Path

import pytest

from arena.agents.random_bot import random_bots
from arena.analytics import match_analytics
from arena.engine.match import Match
from arena.engine.types import Event, EventSource
from arena.games import load_games

EXAMPLES = Path(__file__).resolve().parents[2] / "docs" / "examples"
GAMES = {"liars_deck": 4, "poker": 4, "werewolf": 8}
NAMES = {f"p{i}": f"Seat {chr(64 + i)}" for i in range(1, 9)}  # "Seat A", ...


def example(game):
    data = json.loads((EXAMPLES / f"{game}.json").read_text(encoding="utf-8"))
    return [Event(**{k: v for k, v in e.items() if k != "seq"}) for e in data["events"]]


def report_of(game, events, spoilers=False, names=None):
    return match_analytics(game, events, spoilers, names or {})["report"]


def values(row):
    """A ranking row as key -> value."""
    return {cell["key"]: cell["value"] for cell in row["values"]}


def by_seat(report):
    return {row["seat"]: values(row) for row in report["ranking"]}


@pytest.mark.parametrize(
    ("game", "winners", "length", "turning"),
    [
        ("liars_deck", ["p1"], ("rounds", 10), "p4 is out and the match is decided."),
        ("poker", ["p4"], ("hands", 20), "p4 wins a pot of 2,870."),
        ("werewolf", ["p2", "p4"], ("days", 2), "p3, the villager, was executed by the village."),
    ],
)
def test_the_example_matches_at_a_glance(game, winners, length, turning):
    glance = report_of(game, example(game))["at_a_glance"]

    assert glance["over"] is True
    assert glance["winners"] == winners
    assert (glance["length"]["unit"], glance["length"]["count"]) == length
    assert glance["turning_point"]["text"]["en"] == turning
    assert set(glance["turning_point"]) == {"seq", "kind", "players", "text"}


@pytest.mark.parametrize("game", list(GAMES))
def test_the_ranking_is_in_rank_order_and_every_row_has_every_column(game):
    report = report_of(game, example(game), spoilers=True)

    ranks = [row["rank"] for row in report["ranking"]]
    assert ranks == sorted(ranks)
    keys = [column["key"] for column in report["columns"]]
    for row in report["ranking"]:
        assert [cell["key"] for cell in row["values"]] == keys
        for cell in row["values"]:
            assert cell["better"] in ("higher", "lower", None)
            assert set(cell["label"]) == {"en", "de"}
            if cell["kind"] == "rate" and "n" in cell:
                assert cell["value"] is None or cell["value"] == cell["n"] / cell["of"]


@pytest.mark.parametrize("game", list(GAMES))
def test_spoiler_columns_and_private_counts_are_null_without_spoilers(game):
    shown = report_of(game, example(game), spoilers=True)
    hidden = report_of(game, example(game), spoilers=False)

    secret = {c["key"] for c in hidden["columns"] if c.get("spoilers")}
    assert {"moves", "refused", "fallbacks"} <= secret
    for row in hidden["ranking"]:
        assert all(cell["value"] is None for cell in row["values"] if cell["key"] in secret)
    for key in ("moves", "refused", "fallbacks"):
        assert hidden["at_a_glance"][key] is None
        assert shown["at_a_glance"][key] == sum(v[key] for v in by_seat(shown).values())
    assert shown["at_a_glance"]["tool_errors"] == shown["at_a_glance"]["refused"] > 0


@pytest.mark.parametrize("game", list(GAMES))
def test_key_moments_point_at_their_events_in_order(game):
    events = example(game)
    moments = report_of(game, events)["key_moments"]

    assert moments
    assert [m["seq"] for m in moments] == sorted(m["seq"] for m in moments)
    kinds = {
        "wrong_call": {"cards_revealed"},
        "caught": {"cards_revealed"},
        "eliminated": {"players_eliminated"},
        "winner": {"match_over"},
        "big_pot": {"pot_awarded"},
        "execution": {"player_died"},
        "death": {"player_died"},
        "false_claim": {"message"},
        "counterclaim": {"message"},
    }
    for moment in moments:
        assert events[moment["seq"]].type in kinds[moment["kind"]], moment
        assert moment["importance"] in (1, 2, 3)
        assert moment["text"]["en"] and moment["text"]["de"]
        assert moment["players"] and all(p.startswith("p") for p in moment["players"])


def test_werewolf_rows_show_roles_only_with_spoilers_or_once_revealed():
    shown = by_seat(report_of("werewolf", example("werewolf"), True))
    hidden = by_seat(report_of("werewolf", example("werewolf")))

    assert shown["p2"]["role"] == "werewolf" and hidden["p2"]["role"] is None  # a living wolf
    assert shown["p6"]["role"] == hidden["p6"]["role"] == "witch"  # revealed at death
    assert hidden["p6"]["survived"] is False and hidden["p2"]["survived"] is True


def test_response_time_and_tokens_come_from_decision_events():
    events = example("liars_deck")
    extra = [
        Event(
            source=EventSource.ENGINE,
            type="decision",
            data={"player": "p1", "latency_ms": ms, "tokens_in": 100, "tokens_out": 20},
            visible_to=(),
        )
        for ms in (1000, 3000)
    ]

    report = report_of("liars_deck", events + extra, spoilers=True)

    row = by_seat(report)["p1"]
    assert (row["response_ms_mean"], row["tokens"]) == (2000, 240)
    assert report["at_a_glance"]["response_ms_mean"] == 2000


@pytest.mark.parametrize("game", list(GAMES))
@pytest.mark.parametrize("seed", [1, 2])
def test_bot_matches_have_a_report_in_both_views_that_names_no_seat(game, seed):
    plugin = load_games()[game]
    seats = [f"p{i}" for i in range(1, GAMES[game] + 1)]
    match = Match(plugin, random_bots(plugin, seats, seed), seed=seed)
    asyncio.run(match.run())

    for spoilers in (False, True):
        report = report_of(game, match.events, spoilers, NAMES)
        assert report["at_a_glance"]["over"]
        assert {row["seat"] for row in report["ranking"]} == set(seats)
        for moment in report["key_moments"]:
            for text in moment["text"].values():
                assert not re.search(r"\bp\d\b", text), text
